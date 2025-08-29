"""
HIPAA-compliant web search tool
Ensures PHI is redacted before any external API calls
"""

import re
import logging
from typing import List, Dict, Optional
import asyncio

logger = logging.getLogger(__name__)

# PHI patterns to redact
PHI_PATTERNS = {
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b',
    'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'mrn': r'\b[A-Z]{2,3}\d{6,10}\b',  # Medical Record Numbers
    'dob': r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    'address': r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Plaza|Pl)\b',
    'zip': r'\b\d{5}(?:-\d{4})?\b',
}

def redact_phi(text: str) -> tuple[str, List[str]]:
    """
    Redact PHI from text before external API calls
    
    Returns:
        Tuple of (redacted_text, list_of_redacted_items)
    """
    redacted_items = []
    redacted_text = text
    
    # Apply each PHI pattern
    for phi_type, pattern in PHI_PATTERNS.items():
        matches = re.finditer(pattern, redacted_text, re.IGNORECASE)
        for match in matches:
            original = match.group()
            redacted_items.append({
                'type': phi_type,
                'original': original,
                'position': match.span()
            })
            # Replace with generic placeholder
            redacted_text = redacted_text.replace(original, f"[REDACTED_{phi_type.upper()}]")
    
    # Redact potential names (simple heuristic - words following Mr/Mrs/Dr/etc)
    name_pattern = r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    for match in re.finditer(name_pattern, redacted_text):
        name = match.group(1)
        redacted_items.append({
            'type': 'name',
            'original': name,
            'position': match.span(1)
        })
        redacted_text = redacted_text.replace(name, "[REDACTED_NAME]")
    
    # Log redaction summary (no PHI)
    if redacted_items:
        logger.info(f"Redacted {len(redacted_items)} PHI items before external search")
    
    return redacted_text, redacted_items

async def search_with_phi_protection(
    query: str,
    max_results: int = 5,
    search_engine: str = "stub"
) -> Dict:
    """
    Perform web search with PHI protection
    
    Args:
        query: Search query potentially containing PHI
        max_results: Maximum number of results to return
        search_engine: Search provider to use
    
    Returns:
        Search results with citations
    """
    
    # Redact PHI from query
    safe_query, redacted_items = redact_phi(query)
    
    if redacted_items:
        logger.warning(f"PHI detected and redacted from search query")
    
    # For now, return stub results
    # In production, integrate with actual search API (with BAA if handling PHI)
    
    if search_engine == "stub":
        # Simulated search results
        results = {
            "query": safe_query,
            "original_query_redacted": len(redacted_items) > 0,
            "results": [
                {
                    "title": "Example Medical Information",
                    "url": "https://example.com/medical-info",
                    "snippet": "General medical information about the topic...",
                    "relevance_score": 0.95
                },
                {
                    "title": "Healthcare Best Practices",
                    "url": "https://example.com/best-practices",
                    "snippet": "Industry standards for healthcare delivery...",
                    "relevance_score": 0.87
                },
                {
                    "title": "Clinical Guidelines",
                    "url": "https://example.com/guidelines",
                    "snippet": "Evidence-based clinical guidelines for practitioners...",
                    "relevance_score": 0.82
                }
            ][:max_results],
            "metadata": {
                "search_engine": search_engine,
                "phi_redacted": len(redacted_items) > 0,
                "redaction_count": len(redacted_items)
            }
        }
    else:
        # Placeholder for actual search API integration
        # IMPORTANT: Only use search APIs with BAA for healthcare data
        raise NotImplementedError(f"Search engine '{search_engine}' not yet implemented")
    
    return results

async def validate_search_request(query: str) -> Dict:
    """
    Validate search request for HIPAA compliance
    
    Returns validation status and any warnings
    """
    validation_result = {
        "valid": True,
        "warnings": [],
        "requires_redaction": False
    }
    
    # Check for obvious PHI
    _, redacted_items = redact_phi(query)
    
    if redacted_items:
        validation_result["requires_redaction"] = True
        validation_result["warnings"].append(
            f"Query contains {len(redacted_items)} potential PHI items that will be redacted"
        )
    
    # Check query length
    if len(query) > 1000:
        validation_result["warnings"].append("Query is very long and may be truncated")
    
    # Check for suspicious patterns
    if re.search(r'password|token|secret|key', query, re.IGNORECASE):
        validation_result["warnings"].append("Query may contain sensitive authentication data")
        validation_result["valid"] = False
    
    return validation_result

def format_search_results_for_llm(results: Dict) -> str:
    """
    Format search results for inclusion in LLM context
    """
    if not results.get("results"):
        return "No search results found."
    
    formatted = "Search Results:\n\n"
    
    for i, result in enumerate(results["results"], 1):
        formatted += f"{i}. **{result['title']}**\n"
        formatted += f"   URL: {result['url']}\n"
        formatted += f"   Summary: {result['snippet']}\n"
        if 'relevance_score' in result:
            formatted += f"   Relevance: {result['relevance_score']:.2f}\n"
        formatted += "\n"
    
    if results.get("metadata", {}).get("phi_redacted"):
        formatted += "\n⚠️ Note: PHI was automatically redacted from the search query for compliance.\n"
    
    return formatted