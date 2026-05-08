# SHL Assessment Recommendation Agent: Approach Document
 
 ## 1. Objective
 The goal was to build a conversational AI API that recommends relevant SHL assessments from the SHL Individual Test Solutions catalog. The system needed to support multi-turn conversation, grounded recommendations, and strict response schema compliance.
 
 Required endpoints:
 - GET /health
 - POST /chat
 
 Live deployed URL:
 - https://shl-recommeder.onrender.com
 
 ## 2. Architecture Overview
 I implemented a stateless FastAPI service with three core modules:
 
 1. API Layer (FastAPI)
 - Validates requests and responses using Pydantic models.
 - Exposes /health and /chat endpoints.
 - Enforces schema and safety checks.
 
 2. Agent Layer
 - Handles conversation flow and context extraction.
 - Calls Azure OpenAI for natural language responses.
 - Triggers recommendation generation when enough context is available.
 
 3. Catalog Layer
 - Loads SHL catalog in memory.
 - Performs keyword-based retrieval and scoring.
 - Validates assessment names and URLs before returning output.
 
 This separation made debugging, testing, and iteration easier.
 
 ## 3. Data Preparation
 The SHL catalog data required cleaning due to control-character issues. A cleaning script normalized raw content and produced a valid catalog.json.
 
 Final catalog size:
 - 377 assessments
 
 Each catalog record includes:
 - name
 - url
 - test_type
 - description
 - capabilities
 
 Why in-memory storage:
 - Fast retrieval
 - No DB dependency
 - Simpler deployment and reproducibility
 
 ## 4. Conversation and Recommendation Strategy
 The conversational design follows three stages:
 
 1. Clarification stage
 - Collect role, seniority, and required skill signals.
 
 2. Recommendation stage
 - Generate shortlist (1 to 10 assessments) after sufficient context.
 
 3. Refinement stage
 - Handle follow-up edits or preference updates.
 
 Recommendation pipeline:
 1. Build context from message history.
 2. Extract keywords from role/skills/capabilities.
 3. Score catalog matches by fields (name/description/capabilities).
 4. Apply relevance filters to reduce noisy matches.
 5. Return top ranked validated results.
 
 Grounding rule:
 - Only catalog-validated recommendations are returned in structured output.
 
 ## 5. LLM Design Decisions
 I used Azure OpenAI for conversational response quality and reliability.
 
 Responsibilities assigned to LLM:
 - Natural conversational clarification
 - Recruiter-friendly explanation text
 
 Responsibilities kept deterministic in code:
 - Candidate retrieval/ranking
 - URL validity checks
 - Final structured recommendation output
 
 This hybrid pattern improved reliability versus pure generation.
 
 ## 6. API Contract and Reliability
 The API is stateless: each /chat request includes full conversation history.
 
 Response schema:
 - reply (string)
 - recommendations (array)
 - end_of_conversation (boolean)
 
 Reliability controls:
 - Input validation
 - Turn-limit handling
 - Catalog grounding checks
 - Error-safe fallback messaging
 
 ## 7. Evaluation Approach
 I validated behavior with multi-scenario functional testing and a Recall@10-style heuristic.
 
 Evaluation setup:
 - 10 role scenarios across technical and non-technical profiles.
 - Measured whether recommendation lists contained expected role-signal keywords.
 
 Observed results:
 - Initial heuristic hit rate: ~70%
 - After keyword/ranking refinement: ~87.5%
 
 Noted behavior:
 - Strong performance for explicit technical contexts (Java/Python/JavaScript).
 - Some scenarios were conservative and asked extra clarifying questions before shortlisting.
 
 ## 8. Deployment
 Deployment target:
 - Render web service
 
 Final working configuration:
 - Build command: pip install -r requirements.txt
 - Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
 - Runtime pin: Python 3.11.9 (to avoid pydantic-core build issues)
 
 Environment variables configured on Render:
 - AZURE_OPENAI_API_KEY
 - AZURE_OPENAI_ENDPOINT
 - API_VERSION
 - OPENAI_MODEL_NAME
 - ENVIRONMENT
 
 Production validation:
 - /health returns 200 with status ok
 - /chat returns 200 with required schema
 
 ## 9. Issues Faced and Fixes
 1. Model and quota instability in initial provider setup
 - Fix: Migrated to Azure OpenAI.
 
 2. Environment variable load order issues
 - Fix: Load dotenv before client initialization.
 
 3. Data cleaning failures from invalid control characters
 - Fix: Added pre-processing and sanitized catalog output.
 
 4. Deployment build failure for pydantic-core under Python 3.14
 - Fix: Pinned runtime to Python 3.11.9.
 
 5. Early recommendation noise in ranking
 - Fix: Improved keyword extraction and filtering logic.
 
 ## 10. AI Tool Usage
 AI assistance (GitHub Copilot) was used for:
 - Code scaffolding
 - Refactor support
 - Debugging guidance
 
 Final architecture, trade-offs, testing, and deployment decisions were manually reviewed and validated.
 
 ## 11. Final Outcome
 The solution meets the assignment requirements:
 - Conversational recommendation API implemented
 - Required endpoints exposed and functional
 - Grounded, structured recommendations from SHL catalog
 - Public deployment available
 
 Submission URL:
 - https://shl-recommeder.onrender.com