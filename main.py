"""
SHL Assessment Recommender FastAPI Service.
Provides conversational interface for finding SHL assessments.
"""

import logging
import os
from typing import List, Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Import application modules
from agent import recommender
from catalog import catalog

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SHL Assessment Recommender",
    description="Conversational agent for SHL assessment recommendations",
    version="1.0.0"
)

# Pydantic models for request/response validation
class Message(BaseModel):
    """Represents a single message in the conversation."""
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="The message content")


class ChatRequest(BaseModel):
    """Request body for /chat endpoint."""
    messages: List[Message] = Field(..., description="Conversation history")


class Recommendation(BaseModel):
    """Single assessment recommendation."""
    name: str = Field(..., description="Assessment name")
    url: str = Field(..., description="Assessment URL from catalog")
    test_type: str = Field(..., description="Test type code (e.g., 'K', 'P')")


class ChatResponse(BaseModel):
    """Response body for /chat endpoint."""
    reply: str = Field(..., description="Agent's response")
    recommendations: List[Recommendation] = Field(
        default=[], 
        description="Recommended assessments (empty if still gathering context)"
    )
    end_of_conversation: bool = Field(
        default=False,
        description="True if agent considers conversation complete"
    )


class HealthResponse(BaseModel):
    """Response for /health endpoint."""
    status: str = Field(..., description="Health status")


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for service readiness.
    
    Returns HTTP 200 with status "ok" if service is ready.
    Allows up to 2 minutes for cold start on serverless platforms.
    """
    try:
        # Verify catalog is loaded
        if not catalog.loaded:
            logger.warning("Catalog not loaded during health check")
        
        return HealthResponse(status="ok")
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Main chat endpoint for conversational assessment recommendations.
    
    The API is stateless - the full conversation history is sent with each request.
    
    Args:
        request: ChatRequest with messages list
    
    Returns:
        ChatResponse with agent reply and recommendations (if applicable)
    
    Rules:
    - recommendations: EMPTY when gathering context or refusing
    - recommendations: ARRAY of 1-10 when committed to shortlist
    - end_of_conversation: true only when task complete
    - URLs must come from catalog (no hallucination)
    - Max 8 turns per conversation
    - 30 second timeout per call
    """
    try:
        # Validate request
        if not request.messages:
            raise HTTPException(
                status_code=400,
                detail="messages list cannot be empty"
            )
        
        # Convert Pydantic messages to dict format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        # Check turn count (max 8 turns = max 4 user + 4 assistant)
        user_turns = sum(1 for m in messages if m["role"] == "user")
        assistant_turns = sum(1 for m in messages if m["role"] == "assistant")
        total_turns = user_turns + assistant_turns
        
        if total_turns > 8:
            logger.warning(f"Turn limit exceeded: {total_turns} turns")
            return ChatResponse(
                reply="This conversation has reached its maximum length. Please start a new conversation.",
                recommendations=[],
                end_of_conversation=True
            )
        
        # Get agent response
        agent_response = recommender.chat(messages)
        
        # Validate recommendations (must all be from catalog)
        validated_recommendations = []
        for rec in agent_response.get("recommendations", []):
            # Verify assessment exists in catalog
            assessment = catalog.get_assessment_details(rec["name"])
            if assessment and assessment.get("url") == rec["url"]:
                validated_recommendations.append(Recommendation(
                    name=rec["name"],
                    url=rec["url"],
                    test_type=rec.get("test_type", "U")
                ))
            else:
                logger.warning(f"Rejected invalid recommendation: {rec['name']}")
        
        # Cap recommendations at 10
        validated_recommendations = validated_recommendations[:10]
        
        # Build response
        response = ChatResponse(
            reply=agent_response.get("reply", ""),
            recommendations=validated_recommendations,
            end_of_conversation=agent_response.get("end_of_conversation", False) and len(validated_recommendations) > 0
        )
        
        logger.info(f"Chat response: {len(validated_recommendations)} recommendations, end={response.end_of_conversation}")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting SHL Assessment Recommender service...")
    
    try:
        # Load catalog from JSON file
        try:
            catalog.load_from_file("catalog.json")
            logger.info(f"Loaded {len(catalog.get_all())} assessments from catalog.json")
        except FileNotFoundError:
            logger.warning("catalog.json not found, using sample catalog")
            sample_catalog = [
                {
                    "name": "Java 8 (New)",
                    "url": "https://www.shl.com/en/solutions/products/java-8-new/",
                    "test_type": "K",
                    "description": "Knowledge test for Java 8",
                    "capabilities": ["Java", "Programming", "Technical"]
                },
                {
                    "name": "OPQ32r",
                    "url": "https://www.shl.com/en/solutions/products/opq32r/",
                    "test_type": "P",
                    "description": "Personality assessment",
                    "capabilities": ["Personality", "Behavioral", "Leadership"]
                },
                {
                    "name": "Python Fundamentals",
                    "url": "https://www.shl.com/en/solutions/products/python-fundamentals/",
                    "test_type": "K",
                    "description": "Knowledge test for Python",
                    "capabilities": ["Python", "Programming", "Technical"]
                },
                {
                    "name": "Numerical Reasoning",
                    "url": "https://www.shl.com/en/solutions/products/numerical-reasoning/",
                    "test_type": "A",
                    "description": "Ability test for numerical reasoning",
                    "capabilities": ["Numeracy", "Analysis", "Problem-Solving"]
                },
                {
                    "name": "Verbal Reasoning",
                    "url": "https://www.shl.com/en/solutions/products/verbal-reasoning/",
                    "test_type": "A",
                    "description": "Ability test for verbal reasoning",
                    "capabilities": ["Communication", "Reading", "Analysis"]
                }
            ]
            
            catalog.load_from_json(sample_catalog)
            logger.info(f"Catalog loaded with {len(sample_catalog)} sample assessments")
        
    except Exception as e:
        logger.error(f"Failed to load catalog: {e}")
        # Don't fail startup, but log the error


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down SHL Assessment Recommender service...")


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """Service information endpoint."""
    return {
        "service": "SHL Assessment Recommender",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run with: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
