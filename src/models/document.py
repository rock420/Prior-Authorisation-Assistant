from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date
from pydantic import BaseModel, model_validator, ConfigDict, Field
from enum import Enum


class DocumentType(str, Enum):
    CLINICAL_NOTE = "clinical_note"
    LAB_RESULT = "lab_result"
    IMAGING_REPORT = "imaging_report"
    PRE_OP_EVALUATION = "pre_op_evaluation"
    PRIOR_MEDICAL_HISTORY = "prior_medical_history"
    LETTER_MEDICAL_NECESSITY = "letter_of_medical_necessity"
    CONSENT_FORM = "consent_form"
    AMBIGUOUS = "AMBIGUOUS"
    

class DocumentMetadata(BaseModel):
    """Metadata about a document"""
    model_config = ConfigDict(use_enum_values=True)

    document_id: str
    patient_id: str
    title: str
    document_type: DocumentType
    document_path: str
    created_at: datetime
    is_final: bool = True # vs draft
    tags: Optional[List[str]] = None
    

class RetrievedDocument(BaseModel):
    """A document retrieved from a source system"""
    model_config = ConfigDict(use_enum_values=True)

    metadata: DocumentMetadata
    content_format: str = "text"  # "text", "pdf", "docx"
    binary_content: Optional[bytes] = None


class DocumentMapping(BaseModel):
    """Mapping of a document description to a DocumentType."""
    description: str = Field(description="The original document description")
    document_type: DocumentType = Field(description="The matching DocumentType")
    optional: bool = Field(description="is the document optional")
    keywords: Optional[List[str]] = Field(description="Optional Keywords that will help searching the document")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the mapping")


class DocumentMappingList(BaseModel):
    """List of document mappings."""
    mappings: List[DocumentMapping]
