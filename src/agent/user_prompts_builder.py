from .denial import DenialEvaluationResult
from ..models.integration import PAStatusResponse
from ..models.core import ServiceInfo, ClinicalContext

def build_appeal_user_prompt(
    denial_evaluation: DenialEvaluationResult,
    pa_status: PAStatusResponse,
    service_info: ServiceInfo,
    clinical_context: ClinicalContext
) -> str:
    """Build user prompt for appeal letter generation using DenialEvaluationResult."""
    parts = []

    # Denial information
    parts.append(f"""## Denial Information
- Denial Reason: {pa_status.denial_reason}
- Root Cause: {denial_evaluation.root_cause}
- Decision Details: {pa_status.decision_details}
- Appeal Strength Score: {denial_evaluation.appeal_strength_score}/100""")

    # clinical argument from denial evaluation
    if denial_evaluation.clinical_argument_summary:
        parts.append(f"""## Clinical Argument (from evaluation)
{denial_evaluation.clinical_argument_summary}""")

    # Service details
    parts.append(f"""## Service Details
- CPT Codes: {', '.join(service_info.cpt_codes)}
- HCPCS Codes: {', '.join(service_info.hcpcs_codes) if service_info.hcpcs_codes else 'N/A'}
- Diagnosis Codes (ICD-10): {', '.join(service_info.dx_codes)}
- Site of Service: {service_info.site_of_service}""")

    # Clinical context
    clinical_notes_str = chr(10).join(clinical_context.clinical_notes) if clinical_context.clinical_notes else 'N/A'
    supporting_dx = ', '.join(clinical_context.supporting_diagnoses) if clinical_context.supporting_diagnoses else 'N/A'
    parts.append(f"""## Clinical Context
- Primary Diagnosis: {clinical_context.primary_diagnosis}
- Supporting Diagnoses: {supporting_dx}
- Prior Treatments: {clinical_context.prior_treatments if clinical_context.prior_treatments else 'N/A'}
- Clinical Notes: {clinical_notes_str}""")

    # Evidence gathered during denial evaluation
    if denial_evaluation.evidences:
        evidence_items = []
        for i, e in enumerate(denial_evaluation.evidences, 1):
            evidence_items.append(f"  {i}. [{e.evidence_type}] {e.fact}\n     Source: {e.source} | Relevance: {e.relevance}")
        parts.append(f"""## Gathered Evidence
{chr(10).join(evidence_items)}""")

    # Policy references
    if denial_evaluation.policy_references:
        parts.append(f"""## Applicable Policy References
{chr(10).join(f'- {ref}' for ref in denial_evaluation.policy_references)}""")


    return "Draft appeal letter content based on the following:\n\n" + "\n\n".join(parts)

