"""Data models for tool responses and external system interactions."""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator
from enum import Enum

class PAStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    RFI = "rfi"  # Request for Information

class PHICategory(str, Enum):
    """Categories of Protected Health Information."""
    IDENTIFIERS = "identifiers"      # Name, DOB, address, phone, email
    CLINICAL = "clinical"            # Diagnoses, problem list
    TREATMENT = "treatment"          # Medications, clinical notes
    ENCOUNTERS = "encounters"        # Visit history, providers seen
    COVERAGE = "coverage"            # Insurance info, benefits

class AccessPurpose(str, Enum):
    """Purpose for accessing patient data"""
    PA_SUBMISSION = "pa_submission"
    ELIGIBILITY_CHECK = "eligibility_check"
    CLINICAL_REVIEW = "clinical_review"
    DOCUMENT_COLLECTION = "document_collection"

class PatientDataRequest(BaseModel):
    """Request for patient data with required access controls."""
    patient_id: str = Field(..., description="Unique patient identifier")
    categories: List[PHICategory] = Field(..., description="Categories of data requested")
    purpose: AccessPurpose = Field(..., description="Purpose of data access")
    requester_id: str = Field(..., description="requester id")
    justification: str = Field(..., min_length=10, description="Why this data is needed")

class PatientSummary(BaseModel):
    """Patient summary information from medical records."""
    patient_id: str = Field(..., description="Unique patient identifier")
    demographics: Dict[str, Any] = Field(..., description="Patient demographic information")
    coverage: Dict[str, str] = Field(..., description="Patient coverage information")
    active_problems: List[str] = Field(default_factory=list, description="Current active medical problems")
    medications: List[Dict[str, Any]] = Field(default_factory=list, description="Current medications")
    recent_visits: List[Dict[str, Any]] = Field(default_factory=list, description="Recent medical visits")
    allergies: List[str] = Field(default_factory=list, description="Known allergies")
    last_updated: datetime = Field(..., description="When the summary was last updated")


class CoverageInfo(BaseModel):
    """Patient coverage and eligibility information."""
    eligible: bool = Field(..., description="Whether patient has active coverage")
    plan_details: Dict[str, Any] = Field(..., description="Insurance plan details")
    benefit_information: Dict[str, Any] = Field(default_factory=dict, description="Relevant benefit details")
    copay_info: Optional[Dict[str, Any]] = Field(None, description="Copay and deductible information")
    prior_auth_history: List[Dict[str, Any]] = Field(default_factory=list, description="Previous PA requests")
    verification_date: datetime = Field(default_factory=datetime.utcnow, description="When coverage was verified")


class PARequirement(BaseModel):
    """PA requirement determination from payer systems."""
    required: bool = Field(..., description="Whether PA is required for this service")
    reason: str = Field(..., description="Reason for the requirement determination")
    required_documentation: List[str] = Field(default_factory=list, description="List of required documentation")
    determination_date: datetime = Field(default_factory=datetime.utcnow, description="When determination was made")


class SubmissionResult(BaseModel):
    """Result of PA submission to payer systems."""
    model_config = ConfigDict(validate_assignment=True)

    success: bool = Field(..., description="Whether submission was successful")
    submission_id: Optional[str] = Field(None, description="Payer-assigned submission ID")
    submission_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When submission occurred")
    error_message: Optional[str] = Field(None, description="Error message if submission failed")

    @model_validator(mode='after')
    def validate_submission_id(self):
        """Require submission_id when success."""
        if self.success and not self.submission_id:
            raise ValueError("Submission Id is required")
        return self


class PAStatusResponse(BaseModel):
    """PA status response from payer systems."""
    status: PAStatus = Field(..., description="Current PA status")
    status_date: datetime = Field(..., description="When status was last updated")
    decision_details: Optional[Dict[str, Any]] = Field(None, description="Details of approval/denial/RFI")
    authorization_number: Optional[str] = Field(None, description="Authorization number if approved")
    denial_reason: Optional[str] = Field(None, description="Reason for denial")
    rfi_details: List[str] = Field(None, description="Details of information requested")


class UploadDocument(BaseModel):
    """Information about documents for upload."""
    document_id: str = Field(..., description="Unique document identifier")


class UploadResult(BaseModel):
    """Result of document upload operation."""
    success: bool = Field(..., description="Whether upload was successful")
    uploaded_documents: List[str] = Field(default_factory=list, description="IDs of successfully uploaded documents")
    failed_documents: List[Dict[str, str]] = Field(default_factory=list, description="Documents that failed to upload")
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When upload occurred")
