"""
Conversational agent for SHL assessment recommendations.
Handles multi-turn conversations and generates recommendations.
"""

import json
import logging
import os
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables first
load_dotenv()

from catalog import catalog

logger = logging.getLogger(__name__)

# Configure Azure OpenAI API
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = os.getenv("API_VERSION", "2024-02-15-preview")
AZURE_DEPLOYMENT = os.getenv("OPENAI_MODEL_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

if AZURE_API_KEY and AZURE_ENDPOINT and AZURE_DEPLOYMENT:
    client = AzureOpenAI(
        api_key=AZURE_API_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT
    )
    logger.info("Azure OpenAI API configured")
else:
    client = None
    logger.warning("Azure OpenAI credentials not fully configured in environment")


SYSTEM_PROMPT = """You are an expert SHL assessment recommendation agent. Your job is to help hiring managers find the right SHL assessments for their hiring needs.

## Your Role
1. **Clarify**: Ask clarifying questions to understand what role they're hiring for, seniority level, required skills, and personality aspects
2. **Recommend**: Once you have enough context (typically after 2-3 turns), provide 1-10 assessment recommendations with explanations
3. **Refine**: If the user changes requirements mid-conversation, update your recommendations
4. **Compare**: Answer questions about differences between specific assessments
5. **Refuse**: Only discuss SHL assessments. Refuse general HR advice, legal questions, or off-topic requests

## Important Rules
- **Never recommend without context**: "I need an assessment" is NOT enough. You must clarify the role, seniority, skills needed, etc.
- **Stay grounded**: Only reference assessments from the provided catalog. Never invent assessments.
- **URLs are sacred**: Every URL you provide MUST be from the catalog. Never hallucinate URLs.
- **Concise responses**: Keep replies conversational and focused. Don't overwhelm with information.
- **Max 8 turns**: Plan to provide recommendations by turn 4-6 so we stay within the conversation limit.

## Conversation Flow
1. **Turn 1-2**: Gather job context (role, level, industry, key skills)
2. **Turn 3-4**: Get personality/behavioral preference (if needed)
3. **Turn 4-6**: Provide ranked recommendations (1-10 assessments)
4. **Turn 6+**: Refine, compare, or clarify if needed

## Assessment Context
You have access to the SHL Individual Test Solutions catalog. Key assessment families:
- Ability Tests: Numerical, Verbal, Inductive, Logical
- Personality: OPQ32r, GSA (General Skills Assessment)
- Technical: Java, C++, C#, Python, JavaScript, SQL, etc.
- Domain-specific: Project Management, Sales, Customer Service

## Response Format
When making recommendations, structure your response clearly:
- **Reply**: Natural language explanation (2-3 sentences)
- **Recommendations**: JSON array with name, url, test_type
- **end_of_conversation**: true only when you believe the task is complete
"""


class AssessmentRecommender:
    """Main recommendation agent."""
    
    def __init__(self):
        self.client = client
        self.conversation_history = []
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize Azure OpenAI model."""
        try:
            if self.client:
                logger.info(f"Using Azure OpenAI deployment: {AZURE_DEPLOYMENT}")
            else:
                logger.warning("Azure OpenAI client not initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI: {e}")
    
    def _build_context_summary(self, messages: List[Dict]) -> str:
        """Extract and summarize context from conversation history."""
        # Build a summary of what we know so far
        context_facts = []
        
        for msg in messages:
            if msg["role"] == "user":
                context_facts.append(msg["content"])
        
        return "\n".join(context_facts)
    
    def _extract_recommendations_intent(self, messages: List[Dict]) -> Tuple[bool, Dict]:
        """
        Determine if we should provide recommendations now.
        Returns (should_recommend, context_dict)
        """
        # Count conversation turns
        user_turns = sum(1 for m in messages if m["role"] == "user")
        
        # We need at least 2 user turns to have enough context
        if user_turns < 2:
            return False, {}
        
        # Build context from conversation
        context_text = self._build_context_summary(messages)
        context_lower = context_text.lower()
        
        # Check if we have enough information
        has_role_info = any(word in context_lower for word in [
            'developer', 'java', 'python', 'manager', 'sales', 'customer', 
            'engineer', 'analyst', 'consultant', 'coordinator', 'specialist',
            'role', 'position', 'hiring'
        ])
        
        has_level_info = any(word in context_lower for word in [
            'junior', 'mid', 'mid-level', 'senior', 'lead', 'principal',
            'entry', 'level', 'years', 'experience', 'seniority'
        ])
        
        should_recommend = has_role_info  # At least know the role
        
        return should_recommend, {
            'context_text': context_text,
            'has_role': has_role_info,
            'has_level': has_level_info
        }
    
    def _generate_recommendations(self, messages: List[Dict], context: Dict) -> List[Dict]:
        """Generate assessment recommendations based on context."""
        context_text = context.get('context_text', '')
        
        # Extract keywords from context
        keywords = self._extract_keywords(context_text)
        
        if not keywords:
            return []
        
        # Filter assessments based on keywords
        matching_assessments = catalog.search_by_keywords(keywords, max_results=20)
        
        # Filter out noisy/irrelevant assessments
        noise_keywords = ['electronics', 'telecommunications', 'sap', 'informatica']
        filtered = []
        
        for assessment in matching_assessments:
            name_lower = assessment.get('name', '').lower()
            # Skip if contains noise keywords unless it's a strong role match
            is_noise = any(nk in name_lower for nk in noise_keywords)
            if is_noise:
                # Only keep if also has strong role keyword match
                has_strong_match = any(kw in name_lower for kw in keywords if kw in ['java', 'python', 'javascript', 'sql', 'c#', 'c++'])
                if not has_strong_match:
                    continue
            
            filtered.append(assessment)
        
        # Build recommendations with required fields
        recommendations = []
        for assessment in filtered[:10]:
            rec = {
                "name": assessment.get('name', 'Unknown'),
                "url": assessment.get('url', ''),
                "test_type": assessment.get('test_type', 'U')
            }
            if rec['url']:  # Only add if we have a URL
                recommendations.append(rec)
        
        return recommendations[:10]  # Max 10 recommendations
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for catalog search."""
        # Enhanced keyword extraction with weighted domains
        text_lower = text.lower()
        
        # Primary role/skill keywords (high priority)
        primary_keywords = [
            'java', 'python', 'javascript', 'c#', 'c++', 'sql', 'asp.net', '.net',
            'developer', 'engineer', 'analyst', 'manager', 'sales', 'customer',
            'finance', 'project', 'leadership', 'communication', 'support'
        ]
        
        # Ability/trait keywords (medium priority)
        ability_keywords = [
            'reasoning', 'numerical', 'verbal', 'logical', 'inductive', 'deductive',
            'problem solving', 'debugging', 'analytical', 'cognitive', 'decision making',
            'communication', 'composure', 'service', 'persuasion', 'drive'
        ]
        
        # Extract matched keywords
        keywords = []
        for kw in primary_keywords:
            if kw in text_lower:
                keywords.append(kw)
        
        for kw in ability_keywords:
            if kw in text_lower:
                keywords.append(kw)
        
        # Remove duplicates but preserve order
        seen = set()
        unique = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        
        return unique
    
    def _call_azure_openai(self, messages: List[Dict], system_prompt: str) -> str:
        """Call Azure OpenAI API with conversation history."""
        try:
            if not self.client:
                return "I'm having difficulty connecting to my language model. Please try again."
            
            # Build messages for OpenAI API
            openai_messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            for msg in messages:
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Call Azure OpenAI
            response = self.client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=openai_messages,
                temperature=0.7,
                max_tokens=300,
            )
            
            return response.choices[0].message.content.strip() if response.choices[0].message.content else "I'm unable to generate a response. Please try again."
        except Exception as e:
            logger.error(f"Error calling Azure OpenAI: {e}")
            return "I'm having difficulty connecting to my language model. Please try again."
    
    def chat(self, messages: List[Dict]) -> Dict:
        """
        Process a chat message and return response with recommendations if applicable.
        
        Args:
            messages: List of message dicts with 'role' (user/assistant) and 'content'
        
        Returns:
            Dict with 'reply', 'recommendations' (empty or list), 'end_of_conversation'
        """
        try:
            # Validate input
            if not messages or len(messages) == 0:
                return {
                    "reply": "Hello! I'm here to help you find the right SHL assessments. What role are you looking to hire for?",
                    "recommendations": [],
                    "end_of_conversation": False
                }
            
            # Check if we should provide recommendations
            should_recommend, context = self._extract_recommendations_intent(messages)
            
            # Generate response
            response_text = self._call_azure_openai(messages, SYSTEM_PROMPT)
            
            # Generate recommendations if appropriate
            recommendations = []
            end_conversation = False
            
            if should_recommend and "recommend" in response_text.lower():
                recommendations = self._generate_recommendations(messages, context)
                end_conversation = len(recommendations) > 0
            
            return {
                "reply": response_text,
                "recommendations": recommendations,
                "end_of_conversation": end_conversation
            }
        
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return {
                "reply": "I encountered an error processing your request. Please try again.",
                "recommendations": [],
                "end_of_conversation": False
            }


# Global agent instance
recommender = AssessmentRecommender()
