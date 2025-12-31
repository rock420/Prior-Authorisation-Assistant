"""LangGraph state schema and management for PA Healthcare Agent."""

import operator
from typing import List, Optional, Dict, Any, Annotated, TypedDict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
from langgraph.graph import MessagesState

from ..models import (
    PARequest, 
    PAWorkFlowStatus, 
    UrgencyLevel,
    ServiceInfo, 
    PayerInfo, 
    ProviderInfo,
    ClinicalContext,
    AuditEntry,
    PAStatusResponse,
    UploadDocument
)
from ..models.document import DocumentMapping, DocumentMetadata
from ..models.hitl import HITLTask
from .denial import DenialEvaluationResult
from .requirement import RequireItem, RequireItemResult



class PAIntake(BaseModel):
    """PA intake form data."""
    pa_request_id: str = Field(..., description="Unique PA request identifier")
    patient_name: str = Field(..., description="Patient's full name")
    patient_id: str = Field(..., description="Patient's medical record number")
    provider_id: str = Field(..., description="Provider/clinician ID")
    primary_diagnosis: str = Field(..., description="Primary diagnosis")
    secondary_diagnoses: List[str] = Field(default_factory=list, description="Secondary diagnoses")
    service_info: ServiceInfo = Field(..., description="Medical Service information")
    clinical_notes: Optional[List[str]] = Field(default_factory=list, description="Clinical notes supporting the request")
    supporting_documents: Optional[List[DocumentMetadata]] = Field(default_factory=list, description="Supporting document references")    
    additional_notes: Optional[str] = Field(None, description="Additional notes")
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_by: str = Field(..., description="Clinician who submitted the request")


class PAAgentState(MessagesState):
    # Core PA request data
    pa_request_id: str
    patient_name: str
    patient_id: str
    service_info: ServiceInfo
    clinical_context: ClinicalContext
    payer_info: PayerInfo
    provider_info: ProviderInfo
    additional_notes: Optional[str]
    clinician_id: str

    # PA requirement
    is_pa_required: bool
    require_items: List[RequireItem]
    requirement_result: List[RequireItemResult]

    # Validations
    missing_fields: List[str]
    validation_errors: List[str]

    awaiting_clinician_input: bool
    pending_hitl_task: Optional[HITLTask]
    audit_log: List[AuditEntry]

    #PA submission
    submission_id: str
    uploaded_documents: Annotated[List[UploadDocument], operator.add]
    submission_timestamp: datetime
    status: PAStatusResponse

    #Denial evaluation
    denial_evaluation: DenialEvaluationResult

    workflow_status: PAWorkFlowStatus
