"""Appeal letter templates and models for PA denial appeals."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class AppealLetterSection(BaseModel):
    """A section of the appeal letter with template and generated content."""
    section_name: str
    template: str
    content: str = ""


class AppealLetterContent(BaseModel):
    """LLM-generated content for appeal letter dynamic sections."""
    clinical_justification: str = Field(..., description="Clinical reasoning for medical necessity")
    denial_rebuttal: str = Field(..., description="Point-by-point rebuttal of denial reasons")
    supporting_evidence_summary: str = Field(..., description="Summary of supporting clinical evidence")


APPEAL_LETTER_TEMPLATE = """
{header}

{date}

{payer_address}

RE: Appeal of Prior Authorization Denial
Patient Name: {patient_name}
Patient ID: {patient_id}
Member ID: {member_id}
Original PA Request ID: {pa_request_id}
Date of Denial: {denial_date}
Service Requested: {service_description}

Dear Medical Director / Appeals Department:

I am writing on behalf of {patient_name} to formally appeal the denial of prior authorization for the requested medical service(s). This appeal is submitted in accordance with the patient's right to appeal under their health plan benefits.

DENIAL INFORMATION:
The prior authorization request was denied for the following reason:
{denial_reason}

CLINICAL JUSTIFICATION FOR MEDICAL NECESSITY:
{clinical_justification}

RESPONSE TO DENIAL REASON:
{denial_rebuttal}

SUPPORTING CLINICAL EVIDENCE:
{supporting_evidence_summary}


REQUESTED ACTION:
Based on the clinical evidence and medical necessity documented above, we respectfully request that you reconsider and approve the prior authorization for the requested service(s).

Please contact our office if you require any additional information to process this appeal.

Sincerely,

{provider_name},
{provider_organization}
NPI: {provider_npi}
Phone: {provider_phone}
{provider_address}

{footer}
"""

STANDARD_FOOTER = """
---
This appeal is submitted in compliance with applicable state and federal regulations governing the appeals process for prior authorization denials. The patient reserves all rights under their health plan and applicable law.
"""


def build_appeal_letter(
    patient_name: str,
    patient_id: str,
    member_id: str,
    pa_request_id: str,
    denial_date: datetime,
    denial_reason: str,
    service_description: str,
    provider_name: str,
    provider_organization: str,
    provider_npi: str,
    provider_phone: str,
    provider_address: str,
    payer_name: str,
    payer_address: str,
    content: AppealLetterContent,
    additional_documents: Optional[List[str]] = None,
) -> str:
    """Build a complete appeal letter from template and generated content."""
    
    # Format the complete letter
    letter = APPEAL_LETTER_TEMPLATE.format(
        header=f"APPEAL OF PRIOR AUTHORIZATION DENIAL",
        date=datetime.now().strftime("%B %d, %Y"),
        payer_address=f"{payer_name}\n{payer_address}",
        patient_name=patient_name,
        patient_id=patient_id,
        member_id=member_id,
        pa_request_id=pa_request_id,
        denial_date=denial_date.strftime("%B %d, %Y") if denial_date else "N/A",
        service_description=service_description,
        denial_reason=denial_reason,
        clinical_justification=content.clinical_justification,
        denial_rebuttal=content.denial_rebuttal,
        supporting_evidence_summary=content.supporting_evidence_summary,
        literature_section=literature_section,
        provider_name=provider_name,
        provider_organization=provider_organization,
        provider_npi=provider_npi,
        provider_phone=provider_phone,
        provider_address=provider_address,
        footer=STANDARD_FOOTER,
    )
    
    return letter.strip()
