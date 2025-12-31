"""State schema for the denial evaluator agent."""

import operator
from typing import List, Optional, Dict, Any, Literal, Annotated
from datetime import datetime
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from enum import Enum

from ...models import ServiceInfo, ClinicalContext, UploadDocument

class DenialCategory(str, Enum):
    """Categories of PA denial reasons."""
    MEDICAL_NECESSITY = "medical_necessity"
    MISSING_DOCUMENTATION = "missing_documentation"
    MISSING_DETAILS = "missing_details"
    INCORRECT_CODE = "incorrect_code"
    STEP_THERAPY_NOT_MET = "step_therapy_not_met"
    EXPERIMENTAL_TREATMENT = "experimental_treatment"
    COVERAGE_EXCLUSION = "coverage_exclusion"
    PLACE_OF_SERVICE = "place_of_service"
    OTHER = "other"

REVISE_CATEGORIES = [DenialCategory.MISSING_DOCUMENTATION, DenialCategory.INCORRECT_CODE, DenialCategory.MISSING_DETAILS]

class RecommendedAction(str, Enum):
    """Recommended next steps after denial evaluation."""
    APPEAL = "appeal"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    FINAL_DENIAL = "final_denial"


class DenialDetails(BaseModel):
    """Details about the denial being evaluated."""
    denial_reason: str = Field(None, description="Reason for denial")
    decision_details: Optional[Dict[str, Any]] = Field(None, description="Details of denial")

class DenialCategorization(BaseModel):
    category: DenialCategory = Field(..., description="The categorized denial type")
    root_cause: str = Field(..., description="Root cause for the denial")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in categorization")

class GapAnalysis(BaseModel):
    """Analysis of gaps between denial and supporting documentation."""
    required_evidence: List[str] = Field(..., description="List of evidence requirements to close the gap")
    identified_gaps: List[str] = Field(..., description="Gaps found for the denial reason")
    search_plan: List[str] = Field(..., description="Specific instructions/plan for gathering data using EHR/Policy/Medical research tools")
    policy_references: List[str] = Field(default_factory=list, description="Relevant section/page references from policy document")
    rationale: str = Field(default="", description="explanation for the required_evidence and search plan")
    
class Evidence(BaseModel):
    """Evidence gathered during gap analysis."""
    source: str = Field(..., description="Where evidence was found, mention specific section/page reference and source type")
    evidence_type: str = Field(..., description="Type of evidence (e.g., 'clinical_guideline', 'lab_result', 'policy', etc.)")
    fact: str = Field(..., description="The actual evidence content as it's")
    relevance: float = Field(..., ge=0.0, le=1.0, description="Relevance score as a decimal between 0.0 and 1.0")

class EvidenceGathering(BaseModel):
    found_evidences: List[Evidence] = Field(..., description="List of evidence gathered")
    missing_evidence: List[str] = Field(..., description="List of evidence you couldn't find")

class Judgement(BaseModel):
    recommendation: RecommendedAction = Field(..., description="Recommended next step based on evidence gathered")
    rationale: str = Field(..., description="Internal technical explanation of why this path was chosen.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in recommendation")
    evidence_citations: List[int] = Field(..., description="List of indices of found evidence used in this judgement, 0 based indexing")

    appeal_strength_score: int = Field(ge=0, le=100, description="Confidence score (0-100) in winning the appeal if recommendation is Appeal")
    clinical_argument_summary: Optional[str] = Field(description="The 'Bridge' argument: Why the found evidence satisfies the payer policy, if recommendation is Appeal" )
    required_documentation: Optional[List[str]] = Field(default_factory=list, description="Documents needed if resubmitting or appeal")

    write_off_reason: Optional[str] = Field(description="Why we should stop: e.g., 'Policy explicitly excludes this service under all conditions'.")
    require_more_evidence: Optional[List[str]] = Field(default_factory=list, description="If more evidence is needed, list what that is")
    search_plan: List[str] = Field(..., description="Specific instructions/plan for gathering data using EHR/Policy/Medical research tools")


class DenialEvaluatorState(MessagesState):
    """State for the denial evaluator agent."""
    
    # Input context
    denial_details: DenialDetails
    service_details: ServiceInfo
    clinical_context: ClinicalContext
    documents_shared: List[UploadDocument]

    # Categorization output
    category: DenialCategory
    root_cause: str

    # Gap analysis output
    required_evidence: List[str]
    search_plan: List[str]
    policy_references: List[str]

    #Evidence gatherer
    found_evidence: Annotated[List[Evidence], operator.add]
    missing_evidence: List[str]

    #Judge
    recommendation: RecommendedAction
    judgement: Judgement
    revision_count: int
    

class DenialEvaluationResult(BaseModel):
    root_cause: str
    recommendation: RecommendedAction
    confidence_score: float
    evidences: List[Evidence]
    appeal_strength_score: Optional[int]
    clinical_argument_summary: Optional[str]
    required_documentation: Optional[List[str]]
    policy_references: List[str]
