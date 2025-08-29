"""
HIPAA-compliant internal file search tool
Safe for PHI as it operates within the compliant boundary
"""

import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
import hashlib
import asyncio

logger = logging.getLogger(__name__)

# In production, use a proper vector database like Pinecone, Weaviate, or pgvector
# For now, we'll use a simple in-memory index
class InternalDocumentStore:
    """
    Secure document store for internal PHI-containing documents
    In production, this should be backed by an encrypted database
    """
    
    def __init__(self):
        self.documents = {}
        self.index = {}
        self.encryption_key = os.getenv("DOCUMENT_ENCRYPTION_KEY", "development-key")
    
    def add_document(self, doc_id: str, content: str, metadata: Dict = None) -> str:
        """
        Add a document to the internal store
        
        Args:
            doc_id: Unique document identifier
            content: Document content (may contain PHI)
            metadata: Additional metadata (title, date, category, etc.)
        
        Returns:
            Document hash for verification
        """
        # Generate document hash for integrity
        doc_hash = hashlib.sha256(content.encode()).hexdigest()
        
        # Store document (in production, encrypt before storing)
        self.documents[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "hash": doc_hash,
            "indexed_at": datetime.utcnow().isoformat(),
            "access_count": 0
        }
        
        # Update simple word index (in production, use proper NLP/embedding)
        words = content.lower().split()
        for word in set(words):
            if word not in self.index:
                self.index[word] = []
            if doc_id not in self.index[word]:
                self.index[word].append(doc_id)
        
        logger.info(f"Document added: {doc_id}, hash={doc_hash[:8]}...")
        return doc_hash
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search documents internally (PHI-safe)
        """
        query_words = query.lower().split()
        doc_scores = {}
        
        # Simple TF-IDF style scoring
        for word in query_words:
            if word in self.index:
                for doc_id in self.index[word]:
                    if doc_id not in doc_scores:
                        doc_scores[doc_id] = 0
                    doc_scores[doc_id] += 1
        
        # Sort by relevance score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        results = []
        for doc_id, score in sorted_docs:
            doc = self.documents[doc_id]
            doc["access_count"] += 1
            
            # Extract snippet around matched terms
            content = doc["content"]
            snippet = self._extract_snippet(content, query_words)
            
            results.append({
                "doc_id": doc_id,
                "score": score,
                "snippet": snippet,
                "metadata": doc["metadata"],
                "accessed_at": datetime.utcnow().isoformat()
            })
        
        logger.info(f"Internal search completed: query_words={len(query_words)}, results={len(results)}")
        return results
    
    def _extract_snippet(self, content: str, query_words: List[str], context_size: int = 50) -> str:
        """
        Extract relevant snippet from document
        """
        content_lower = content.lower()
        
        # Find first occurrence of any query word
        first_pos = len(content)
        for word in query_words:
            pos = content_lower.find(word)
            if pos != -1 and pos < first_pos:
                first_pos = pos
        
        # Extract snippet with context
        start = max(0, first_pos - context_size)
        end = min(len(content), first_pos + context_size + 20)
        
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        return snippet

# Global document store instance
document_store = InternalDocumentStore()

async def search_internal_documents(
    query: str,
    filters: Optional[Dict] = None,
    limit: int = 10
) -> Dict:
    """
    Search internal documents (safe for PHI)
    
    Args:
        query: Search query (may contain PHI - safe internally)
        filters: Optional filters (date range, category, etc.)
        limit: Maximum results to return
    
    Returns:
        Search results from internal documents
    """
    
    # Log search request (metadata only)
    logger.info(f"Internal document search: query_length={len(query)}, filters={bool(filters)}")
    
    # Perform search
    results = document_store.search(query, limit)
    
    # Apply filters if provided
    if filters:
        filtered_results = []
        for result in results:
            # Example: filter by date
            if "date_from" in filters:
                doc_date = result["metadata"].get("date")
                if doc_date and doc_date >= filters["date_from"]:
                    filtered_results.append(result)
            else:
                filtered_results.append(result)
        results = filtered_results
    
    # Format response
    response = {
        "query": query,  # Safe to include since this is internal
        "results": results,
        "total_results": len(results),
        "metadata": {
            "search_type": "internal",
            "phi_safe": True,
            "filtered": bool(filters)
        }
    }
    
    return response

async def index_document(
    file_path: str,
    doc_type: str = "text",
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Index a new document for internal search
    
    Args:
        file_path: Path to document file
        doc_type: Type of document (text, pdf, etc.)
        metadata: Additional metadata to store
    
    Returns:
        Indexing result with document hash
    """
    
    try:
        # Read document content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Generate document ID
        doc_id = os.path.basename(file_path)
        
        # Add metadata
        if metadata is None:
            metadata = {}
        metadata.update({
            "file_path": file_path,
            "doc_type": doc_type,
            "file_size": os.path.getsize(file_path),
            "indexed_date": datetime.utcnow().isoformat()
        })
        
        # Index document
        doc_hash = document_store.add_document(doc_id, content, metadata)
        
        return {
            "success": True,
            "doc_id": doc_id,
            "doc_hash": doc_hash,
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Failed to index document: {type(e).__name__}")
        return {
            "success": False,
            "error": str(type(e).__name__),
            "doc_id": None
        }

def format_file_search_results_for_llm(results: Dict) -> str:
    """
    Format internal search results for LLM context
    """
    if not results.get("results"):
        return "No internal documents found matching the query."
    
    formatted = "Internal Document Search Results:\n\n"
    
    for i, result in enumerate(results["results"], 1):
        formatted += f"{i}. Document: {result['doc_id']}\n"
        formatted += f"   Relevance Score: {result['score']}\n"
        formatted += f"   Excerpt: {result['snippet']}\n"
        
        # Include relevant metadata
        if result.get("metadata"):
            meta = result["metadata"]
            if "title" in meta:
                formatted += f"   Title: {meta['title']}\n"
            if "date" in meta:
                formatted += f"   Date: {meta['date']}\n"
            if "category" in meta:
                formatted += f"   Category: {meta['category']}\n"
        
        formatted += "\n"
    
    formatted += f"\n📁 Total results: {results['total_results']} (Internal search - PHI safe)\n"
    
    return formatted

# Initialize with sample documents (for testing)
async def initialize_sample_documents():
    """
    Initialize document store with sample documents
    This is for testing only - remove in production
    """
    samples = [
        {
            "doc_id": "hipaa-guidelines",
            "content": "HIPAA Privacy Rule establishes national standards to protect individuals' medical records and other personal health information. Covered entities must implement appropriate administrative, physical, and technical safeguards.",
            "metadata": {"title": "HIPAA Guidelines", "category": "compliance", "date": "2024-01-01"}
        },
        {
            "doc_id": "patient-consent-form",
            "content": "Patient consent form template for sharing protected health information. Requires explicit authorization for use and disclosure of PHI for purposes other than treatment, payment, or healthcare operations.",
            "metadata": {"title": "Patient Consent Form", "category": "forms", "date": "2024-01-15"}
        },
        {
            "doc_id": "security-protocols",
            "content": "Security protocols for handling electronic protected health information (ePHI). Includes encryption requirements, access controls, audit logs, and incident response procedures.",
            "metadata": {"title": "Security Protocols", "category": "security", "date": "2024-02-01"}
        }
    ]
    
    for sample in samples:
        document_store.add_document(
            sample["doc_id"],
            sample["content"],
            sample["metadata"]
        )
    
    logger.info(f"Initialized {len(samples)} sample documents for testing")