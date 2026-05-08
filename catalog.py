"""
Catalog management for SHL assessments.
Loads and maintains the SHL product catalog in memory.
"""

import json
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class SHLCatalog:
    """Manages the SHL assessment catalog."""
    
    def __init__(self):
        self.assessments: List[Dict] = []
        self.by_name: Dict[str, Dict] = {}
        self.loaded = False
    
    def load_from_file(self, filepath: str) -> None:
        """Load catalog from a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.assessments = json.load(f)
            self._build_indexes()
            self.loaded = True
            logger.info(f"Loaded {len(self.assessments)} assessments from {filepath}")
        except Exception as e:
            logger.error(f"Error loading catalog from file: {e}")
            raise
    
    def load_from_json(self, data: List[Dict]) -> None:
        """Load catalog from JSON data."""
        self.assessments = data
        self._build_indexes()
        self.loaded = True
        logger.info(f"Loaded {len(self.assessments)} assessments from JSON data")
    
    def _build_indexes(self) -> None:
        """Build indexes for fast lookup."""
        self.by_name = {a.get('name', ''): a for a in self.assessments}
    
    def get_all(self) -> List[Dict]:
        """Get all assessments."""
        return self.assessments
    
    def get_by_name(self, name: str) -> Optional[Dict]:
        """Get assessment by name."""
        return self.by_name.get(name)
    
    def search_by_keywords(self, keywords: List[str], max_results: int = 10) -> List[Dict]:
        """
        Search assessments by keywords.
        Returns top max_results matches.
        """
        if not keywords:
            return []
        
        # Score each assessment by keyword matches
        scored = []
        keywords_lower = [k.lower() for k in keywords]
        
        for assessment in self.assessments:
            score = 0
            
            # Search in name
            name_lower = assessment.get('name', '').lower()
            for keyword in keywords_lower:
                if keyword in name_lower:
                    score += 3
            
            # Search in description
            desc_lower = assessment.get('description', '').lower()
            for keyword in keywords_lower:
                if keyword in desc_lower:
                    score += 1
            
            # Search in capabilities
            caps = assessment.get('capabilities', [])
            for cap in caps:
                for keyword in keywords_lower:
                    if keyword in cap.lower():
                        score += 2
            
            if score > 0:
                scored.append((score, assessment))
        
        # Sort by score (descending) and return top results
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:max_results]]
    
    def filter_by_criteria(self, criteria: Dict) -> List[Dict]:
        """
        Filter assessments by criteria.
        
        Criteria keys:
        - test_types: List of test types (e.g., ["K", "P"])
        - seniority: List of seniority levels
        - keywords: List of keywords
        - capabilities: List of required capabilities
        """
        results = self.assessments
        
        if 'test_types' in criteria:
            test_types = criteria['test_types']
            results = [a for a in results if a.get('test_type') in test_types]
        
        if 'keywords' in criteria:
            keywords = criteria['keywords']
            keyword_matches = self.search_by_keywords(keywords, max_results=len(self.assessments))
            keyword_set = set(a['name'] for a in keyword_matches)
            results = [a for a in results if a['name'] in keyword_set]
        
        if 'capabilities' in criteria:
            required_caps = set(criteria['capabilities'])
            results = [
                a for a in results 
                if required_caps.issubset(set(a.get('capabilities', [])))
            ]
        
        return results
    
    def get_assessment_details(self, name: str) -> Optional[Dict]:
        """Get full details of an assessment."""
        return self.by_name.get(name)
    
    def validate_assessment_exists(self, name: str) -> bool:
        """Check if an assessment exists in the catalog."""
        return name in self.by_name


# Global catalog instance
catalog = SHLCatalog()
