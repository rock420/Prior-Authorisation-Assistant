"""State schema for the Requirement handler agent."""

import operator
from typing import List, Optional, Dict, Any, Literal, Annotated, TypedDict
from datetime import datetime
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from enum import Enum

from ...models.core import ServiceInfo, ClinicalContext
from ...models.document import DocumentType, DocumentMetadata
from ...models.hitl import HITLTask


class RequireItemStatus(str, Enum):
    """Status of individual items."""
    PENDING = "pending"
    FOUND = "found"
    PARTIALLY_FOUND = "partially_found"
    NOT_FOUND = "not_found"


class ParsedRequireItem(BaseModel):
    """Individual item requested."""
    item_id: str = Field(..., description="Unique identifier for this item")
    original_request: str = Field(..., description="Original request text")
    optional: bool = Field(..., description="If this requirement is optional, cases like if available")
    description: str = Field(..., description="Description of requested information")
    document_type: Optional[DocumentType] = Field(None, description="Mapped document type if applicable")
    keywords: List[str] = Field(default_factory=list, description="Keywords for searching")

class ParsedRequireItemList(BaseModel):
    """List of parsed items."""
    items: List[ParsedRequireItem] = Field(default_factory=list, description="List of items")

class DocumentInfo(BaseModel):
    document_id: str = Field(..., description="Document identifier")
    title: str = Field(..., description="Document title")
    document_type: DocumentType = Field(..., description="Type of document")
    summary: str = Field(..., description="Document summary")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to requirement request")

# Structured output for Gatherer
class GathererResult(BaseModel):
    """Result from the gatherer agent's search."""
    status: RequireItemStatus = Field(..., description="Status after search based on found documents or information")
    found_documents: List[DocumentInfo] = Field(default_factory=list, description="Documents found")
    found_information: Optional[str] = Field(None, description="Information found")
    search_summary: str = Field(..., description="Summary of search performed")
    supporting_evidence: List[str] = Field(..., description="Evidence supporting the found_information")
    justification: str = Field(..., description="Justification for the search result and why they satisfy the requirement")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in findings")


# Structured output for Evaluator
class EvaluatorVerdict(BaseModel):
    """Verdict from the evaluator on gathered data."""
    satisfies_request: bool = Field(..., description="Whether gathered data satisfies the requested item")
    reasoning: str = Field(..., description="Explanation of evaluation")
    gaps: List[str] = Field(default_factory=list, description="Gaps in the gathered information if any")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for additional searches if major gap")

class RequireItem(BaseModel):
    item_id: str = Field(..., description="Unique identifier for this item")
    requested_item: str = Field(..., description="requested information")

class RequireItemResult(BaseModel):
    """Final result for a single requirement item."""
    item_id: str = Field(..., description="Requirement item ID")
    original_request: str = Field(..., description="Original request description")
    optional: bool = Field(..., description="If this requirement is optional, cases like if available")
    status: RequireItemStatus = Field(..., description="Final status")
    documents: List[DocumentInfo] = Field(default_factory=list, description="Documents to submit")
    information: Optional[str] = Field(None, description="Information to include in response")
    supporting_evidence: List[str] = Field(..., description="Evidence supporting the found_information")
    gaps: List[str] = Field(default_factory=list, description="Gaps in the gathered information")


class GathererState(MessagesState):
    parsed_require_item: ParsedRequireItem
    service_details: ServiceInfo
    clinical_context: ClinicalContext
    gather_result: GathererResult
    evaluator_verdict: EvaluatorVerdict

class RequirementAgentState(TypedDict):
    """State for the Requirement handler agent."""
    
    # Input context
    require_items: List[RequireItem]
    service_details: ServiceInfo
    clinical_context: ClinicalContext
    
    # Parsed items
    parsed_require_items: List[ParsedRequireItem]
    
    # Gatherer output
    gatherer_results: Annotated[Dict[int, GathererResult], operator.or_]
    
    # Evaluator output
    evaluator_verdicts: Annotated[Dict[int, EvaluatorVerdict], operator.or_]
    
    # Final output
    require_item_result: List[RequireItemResult]
    
    # Workflow tracking
    processing_complete: bool
