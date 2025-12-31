"""State schema for the denial evaluator agent."""

from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from enum import Enum

from ...models.core import ServiceInfo, ClinicalContext

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


class RecommendedAction(str, Enum):
    """Recommended next steps after denial evaluation."""
    APPEAL = "appeal"
    REVISE_AND_RESUBMIT = "revise_and_resubmit"
    FINAL_DENIAL = "final_denial"


class DenialDetails(BaseModel):
    """Details about the denial being evaluated."""
    denial_reason: str = Field(None, description="Reason for denial")
    decision_details: Optional[Dict[str, Any]] = Field(None, description="Details of denial")


# Structured output for Judge
class JudgeVerdict(BaseModel):
    """Structured verdict from the judge."""
    verdict: Literal["APPROVED", "REVISE"] = Field(..., description="Whether to approve or request revision")
    reasoning: str = Field(..., description="Explanation for the verdict")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions if revision needed")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in verdict")

# Structured output for final result
class EvaluationResult(BaseModel):
    """Final structured evaluation result."""
    denial_category: DenialCategory = Field(..., description="Categorized denial type")
    recommended_action: RecommendedAction = Field(..., description="Recommended next step")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in recommendation")
    justification: str = Field(..., description="Detailed reasoning for the decision about recommended_action")
    supporting_evidence: List[str] = Field(..., description="Evidence supporting the recommendation")
    contradicting_evidence: List[str] = Field(..., description="Evidence that contradicts the denial reason")
    
    # Action-specific details
    required_next_steps: List[str] = Field(..., description="Specific actions needed")
    required_documentation: List[str] = Field(default_factory=list, description="Documents needed if resubmitting or appeal")
    code_corrections: List[str] = Field(default_factory=list, description="List of incorrect codes")


class DenialEvaluatorState(MessagesState):
    """State for the denial evaluator agent."""
    
    # Input context
    denial_details: DenialDetails
    service_details: ServiceInfo
    clinical_context: ClinicalContext
    
    # Evaluator output
    evaluator_decision: str
    tool_call_count: int
    
    # Judge output
    judge_verdict: JudgeVerdict
    revision_count: int
    
    # Final output
    evaluation_result: EvaluationResult

class DenialEvaluationResult(BaseModel):
    evaluation_result: Optional[EvaluationResult]
    judge_verdict: Optional[JudgeVerdict]
    revision_count: int