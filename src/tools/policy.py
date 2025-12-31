"""Policy lookup tools for PA workflow."""

import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime

from ..integrations.payer_service import check_coverage


_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> dict:
    """Load JSON file from mock data directory."""
    filepath = _DATA_DIR / filename
    if not filepath.exists():
        return {}
    with open(filepath) as f:
        return json.load(f)


class PolicyLookup(BaseModel):
    """Request model for policy criteria lookup via semantic search."""
    query: str = Field(
        ..., 
        min_length=3,
        description="Specific search text for fetching relevant policy information"
    )
    keywords: List[str] = Field(
        default_factory=list, 
        description="Specific relevant keywords for hybrid boost (e.g., ['conservative treatment', 'neurological'])"
    )
    top_k: int = Field(
        default=5, 
        ge=1, 
        le=20, 
        description="Number of relevant chunks to return"
    )


class PolicyChunk(BaseModel):
    """A retrieved chunk from policy document."""
    section: Optional[str] = Field(None, description="Section header if available")
    content: str = Field(..., description="The actual policy text content")
    score: float = Field(..., description="Relevance score from search")
    metadata: List[str] = Field(default_factory=list, description="Additional chunk metadata")


def _search_policy_criteria(
    query: str,
    keywords: List[str],
    payer_id: str,
    top_k: int = 5
) -> List[PolicyChunk]:
    """
    Search policy criteria using mock data.
    
    In production, this would use semantic search against a vector database where we have indexed and embedded policy documents
    For now, we do keyword matching against the policy_criteria.json file.
    """
    policy_data = _load_json("policy_criteria.json")
    policies = policy_data.get("policies", {})
    
    results = []
    query_lower = query.lower()
    keywords_lower = [kw.lower() for kw in keywords]
    
    for policy_id, policy in policies.items():
        # Check if policy matches payer
        if policy.get("payer_id") != payer_id:
            continue
        
        sections = policy.get("sections", {})
        
        for section_name, section_data in sections.items():
            content = section_data.get("content", "")
            title = section_data.get("title", section_name)
            content_lower = content.lower()
            
            # Calculate relevance score based on query and keyword matches
            score = 0.0
            
            # Query match
            if query_lower in content_lower:
                score += 0.5
            
            # Partial query word matches
            query_words = query_lower.split()
            matching_words = sum(1 for word in query_words if word in content_lower)
            score += (matching_words / len(query_words)) * 0.3 if query_words else 0
            
            # Keyword matches
            if keywords_lower:
                keyword_matches = sum(1 for kw in keywords_lower if kw in content_lower)
                score += (keyword_matches / len(keywords_lower)) * 0.2
            
            # Only include if there's some relevance
            if score > 0.1:
                results.append(PolicyChunk(
                    section=title,
                    content=content,
                    score=round(score, 2),
                    metadata=[
                        f"policy_id:{policy_id}",
                        f"effective_date:{policy.get('effective_date', 'unknown')}",
                        f"payer:{payer_id}"
                    ]
                ))
    
    # Sort by score descending
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_k]

@tool(
    description="Retrieves specific policy criteria and requirements for a service. ",
    args_schema=PolicyLookup
)
async def lookup_policy_criteria(
    runtime: ToolRuntime, 
    query: str, 
    keywords: List[str] = [], 
    top_k: int = 5
) -> List[PolicyChunk]:
    payer_id = runtime.context.get("payer_id")
    plan_id = runtime.context.get("plan_id")
    
    if not plan_id or not payer_id:
        return []
    
    return _search_policy_criteria(query, keywords, payer_id, top_k)
