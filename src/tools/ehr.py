"""EHR (Electronic Health Record) tools for PA workflow."""

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime

from ..integrations.ehr_service import (
    get_patient_summary,
)
from ..models.integration import PatientDataRequest, AccessPurpose, PHICategory


class PatientHealthRecordInput(BaseModel):
    """Input schema for patient health record retrieval."""
    categories: List[PHICategory] = Field(
        description="Categories of data to retrieve (identifiers, clinical, treatment, encounters, coverage). Each category data is separated, combination doesn't matter"
    )
    purpose: AccessPurpose = Field(
        description="Purpose of data access (pa_submission, eligibility_check, clinical_review, document_collection). For auditing purpose"
    )
    justification: str = Field(
        description="Justification for data access - explain why this data is needed. For auditing purpose"
    )


@tool(
    description="Get patient health details based on requested categories. purpose/justification are for auditing purpose and doesn't change tool response"
                "Use this to retrieve demographics, clinical problems, medications, visit history, and coverage info.",
    args_schema=PatientHealthRecordInput
)
async def get_patient_health_record(
    categories: List[PHICategory], 
    purpose: AccessPurpose, 
    justification: str, 
    runtime: ToolRuntime
):
    patient_id = runtime.context.get("patient_id")
    if not patient_id:
        return f"Error: No details found"
    return get_patient_summary(PatientDataRequest(
        patient_id=patient_id,
        categories=categories,
        purpose=purpose,
        justification=justification,
        requester_id="pa_agent_workflow"
    ))
