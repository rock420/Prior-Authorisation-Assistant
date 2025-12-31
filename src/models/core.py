"""Core data models for the PA Healthcare Agent."""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum

from .validation import ValidationUtils
from .document import DocumentMetadata


class UrgencyLevel(str, Enum):
    """Urgency level for PA requests."""
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENT = "emergent"


class PAWorkFlowStatus(str, Enum):
    """Status of PA request workflow."""
    INTAKE = "intake"
    VALIDATION = "validation"
    COVERAGE_DETERMINATON = "coverage_determination"
    ELIGIBILITY_DETERMINATION = "eligibility_determination"
    REQUIREMENT_COLLECTION = "requirement_collection"
    REQUIREMENT_VALIDATION = "requirement_validation"
    UPLOAD_REQUIREMENTS = "upload_requirements"
    SUBMISSION = "submission"
    TRACKING = "tracking"
    DENIAL_EVALUATION = "denial_evaluation"
    RESOLUTION = "resolution"
    REVISE = "revise"
    APPEAL = "appeal"

class ServiceInfo(BaseModel):
    """Information about the medical service requiring authorization."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    cpt_codes: List[str] = Field(..., description="Current Procedural Terminology codes")
    hcpcs_codes: List[str] = Field(default_factory=list, description="Healthcare Common Procedure Coding System codes")
    dx_codes: List[str] = Field(..., description="ICD-10 diagnosis codes")
    site_of_service: str = Field(..., description="Location where service will be provided")
    requested_units: int = Field(..., gt=0, description="Number of units requested")
    service_start_date: datetime = Field(..., description="Requested service start date")
    service_end_date: datetime = Field(..., description="Requested service end date")
    urgency_level: UrgencyLevel = Field(default=UrgencyLevel.ROUTINE, description="Urgency of the request")

    @field_validator('cpt_codes', 'hcpcs_codes', 'dx_codes')
    @classmethod
    def validate_codes(cls, v, info):
        """Validate that codes are non-empty strings and have correct format."""
        if not v:  # Allow empty lists
            return v
        
        field_name = info.field_name
        incorrect_codes = []
        if field_name == 'cpt_codes':
            incorrect_codes =  ValidationUtils.validate_medical_codes(v, 'cpt')
        elif field_name == 'hcpcs_codes':
            incorrect_codes =  ValidationUtils.validate_medical_codes(v, 'hcpcs')
        elif field_name == 'dx_codes':
            incorrect_codes = ValidationUtils.validate_medical_codes(v, 'icd10')
        
        if incorrect_codes:
            raise ValueError(f"Invalid {field_name} formats: {incorrect_codes}")
        
        return v

    @model_validator(mode='after')
    def validate_service_dates(self):
        """Validate that service end date is after start date."""
        if self.service_end_date < self.service_start_date:
            raise ValueError("Service end date must be after start date")
        return self


class ClinicalContext(BaseModel):
    """Clinical information supporting the PA request."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    primary_diagnosis: str = Field(..., description="Primary diagnosis for the service")
    supporting_diagnoses: List[str] = Field(default_factory=list, description="Additional relevant diagnoses")
    relevant_history: List[str] = Field(default_factory=list, description="Relevant medical history")
    prior_treatments: List[Dict[str, Any]] = Field(default_factory=list, description="Previous treatments attempted")
    clinical_notes: List[str] = Field(default_factory=list, description="Clinical notes supporting the request")
    supporting_documents: List[DocumentMetadata] = Field(default_factory=list, description="References to supporting documentation")

    # @field_validator('primary_diagnosis')
    # @classmethod
    # def validate_primary_diagnosis(cls, v):
    #     """Validate primary diagnosis is not empty and has correct ICD-10 format."""
    #     if not v or not v.strip():
    #         raise ValueError("Primary diagnosis cannot be empty")
        
    #     cleaned = v.strip().upper()
    #     if not ValidationUtils.validate_icd10_code(cleaned):
    #         raise ValueError(f"Invalid ICD-10 code format: {cleaned}")
        
    #     return cleaned


class PayerInfo(BaseModel):
    """Information about the patient's insurance payer."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    payer_id: str = Field(..., description="Unique identifier for the payer")
    payer_name: str = Field(..., description="Name of the payer")
    plan_id: str = Field(..., description="Specific plan identifier")
    plan_name: str = Field(..., description="Plan name")
    member_id: str = Field(..., description="Patient's member ID")
    effective_date: datetime = Field(..., description="Coverage effective date")
    termination_date: Optional[datetime] = Field(None, description="Coverage termination date")

    @field_validator('termination_date')
    @classmethod
    def validate_termination_date(cls, v, info):
        """Validate termination date is after effective date."""
        if v and 'effective_date' in info.data and v <= info.data['effective_date']:
            raise ValueError("Termination date must be after effective date")
        return v


class ProviderInfo(BaseModel):
    """Information about the healthcare provider requesting authorization."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    provider_id: str = Field(..., description="Unique identifier for the provider")
    npi: str = Field(..., description="National Provider Identifier")
    name: str = Field(..., description="Provider's full name")
    organization: str = Field(..., description="Healthcare organization/facility name")
    phone: str = Field(..., description="Provider contact phone number")
    email: Optional[str] = Field(None, description="Provider contact email")
    address: Dict[str, str] = Field(..., description="Provider's address")
    license_number: str = Field(..., description="Medical license number")
    
    @field_validator('npi')
    @classmethod
    def validate_npi(cls, v):
        """Validate NPI format (10 digits)."""
        if not ValidationUtils.validate_npi(v):
            raise ValueError(f"NPI must be exactly 10 digits, got: {v}")
        return v
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        """Validate phone number format."""
        sanitized = ValidationUtils.sanitize_phone(v)
        if not ValidationUtils.validate_phone(v):
            raise ValueError(f"Phone number must contain exactly 10 digits, got: {v}")
        return sanitized
    
    @field_validator('address')
    @classmethod
    def validate_address(cls, v):
        """Validate required address fields."""
        missing_fields = ValidationUtils.validate_address_completeness(v)
        if missing_fields:
            raise ValueError(f"Address missing required fields: {missing_fields}")
        return v


class AuditEntry(BaseModel):
    """Audit trail entry for system actions."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the action occurred")
    user_id: str = Field(..., description="User who initiated the action")
    action_type: str = Field(..., description="Type of action performed")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: str = Field(..., description="ID of the resource affected")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional action details")
    phi_accessed: bool = Field(default=False, description="Whether PHI was accessed")
    justification: Optional[str] = Field(None, description="Justification for PHI access")

    @model_validator(mode='after')
    def validate_phi_justification(self):
        """Require justification when PHI is accessed."""
        if self.phi_accessed and not self.justification:
            raise ValueError("Justification required when PHI is accessed")
        return self


class PARequest(BaseModel):
    """Core PA request object containing all workflow information."""
    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)
    
    id: str = Field(..., description="Unique identifier for the PA request")
    patient_id: str = Field(..., description="Patient identifier")
    requesting_provider: ProviderInfo = Field(..., description="Provider requesting the authorization")
    service_details: ServiceInfo = Field(..., description="Details of the service requiring authorization")
    clinical_context: ClinicalContext = Field(..., description="Clinical information supporting the request")
    payer_info: PayerInfo = Field(..., description="Patient's insurance information")
    audit_trail: List[AuditEntry] = Field(default_factory=list, description="Complete audit trail")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the request was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When the request was last updated")
    submission_id: Optional[str] = Field(None, description="Payer submission ID when submitted")
    decision_details: Optional[Dict[str, Any]] = Field(None, description="Final decision details")

    def add_audit_entry(self, user_id: str, action_type: str, resource_type: str, 
                       resource_id: str, details: Optional[Dict[str, Any]] = None,
                       phi_accessed: bool = False, justification: Optional[str] = None) -> None:
        """Add an audit entry to the request."""
        entry = AuditEntry(
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            phi_accessed=phi_accessed,
            justification=justification
        )
        self.audit_trail.append(entry)
        self.updated_at = datetime.utcnow()

class Appeal(BaseModel):
    """Structured appeal documentation for PA denials."""
    appeal_id: str = Field(..., description="Unique appeal identifier")
    original_pa_request_id: str = Field(..., description="Original PA request being appealed")
    denial_details: Dict[str, Any] = Field(..., description="Details of the original denial")
    
    appeal_type: str = Field(..., description="Type of appeal (medical necessity, coverage, etc.)")
    denial_category: str = Field(..., description="Categorized reason for denial")
    
    clinical_justification: str = Field(..., description="Clinical justification for the appeal")
    supporting_evidence: List[str] = Field(default_factory=list, description="Supporting evidence and documentation")
    medical_literature: List[Dict[str, str]] = Field(default_factory=list, description="Relevant medical literature")
    
    draft_id: str = Field(..., description="Draft appeal letter id")
    required_approvals: List[str] = Field(..., description="Staff roles required to approve appeal")
    approvals_received: List[Dict[str, Any]] = Field(default_factory=list, description="Approvals received")
    
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When appeal packet was created")
    
    approved_for_submission: bool = Field(default=False, description="Whether appeal is approved for submission")
    submitted_at: Optional[datetime] = Field(None, description="When appeal was submitted")
    submission_id: Optional[str] = Field(None, description="Payer submission ID for appeal")

    def add_approval(self, approver: str, role: str, notes: Optional[str] = None) -> None:
        """Add an approval to the appeal packet."""
        approval = {
            "approver": approver,
            "role": role,
            "timestamp": datetime.utcnow(),
            "notes": notes
        }
        self.approvals_received.append(approval)
        
        # Check if all required approvals are received
        approved_roles = {approval["role"] for approval in self.approvals_received}
        if all(role in approved_roles for role in self.required_approvals):
            self.approved_for_submission = True

    def is_ready_for_submission(self) -> bool:
        """Check if appeal has all required approvals."""
        return self.approved_for_submission
