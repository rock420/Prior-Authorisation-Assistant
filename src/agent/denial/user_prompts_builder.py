import json
from .state import DenialEvaluatorState

def build_categorizer_user_prompt(state: DenialEvaluatorState) -> str:
    """Build user prompt for the categorizer agent."""
    parts = []

    # Denial information
    if state.get("denial_details"):
        denial = state["denial_details"]
        parts.append(f"""## Denial Information
- Denial Reason: {denial.denial_reason or 'Not provided'}
- Decision Details: {json.dumps(denial.decision_details) if denial.decision_details else 'Not provided'}""")

    # Service information
    if state.get("service_details"):
        service = state["service_details"]
        parts.append(f"""## Service Information
- CPT Codes: {service.cpt_codes}
- HCPCS Codes: {service.hcpcs_codes}
- Diagnosis Codes (ICD-10): {service.dx_codes}
- Site of Service: {service.site_of_service}
- Urgency Level: {service.urgency_level}""")

    # Clinical context
    if state.get("clinical_context"):
        clinical = state["clinical_context"]
        parts.append(f"""## Clinical Context
- Primary Diagnosis: {clinical.primary_diagnosis}
- Supporting Diagnoses: {clinical.supporting_diagnoses}
- Relevant History: {clinical.relevant_history}
- Prior Treatments: {clinical.prior_treatments}
- Clinical Notes: {clinical.clinical_notes}""")

    return "Categorize this PA denial:\n\n" + "\n\n".join(parts)


def build_gap_analysis_user_prompt(state: DenialEvaluatorState) -> str:
    """Build user prompt for the gap analysis agent."""
    parts = []

    # Categorization result
    parts.append(f"""## Denial Categorization
- Category: {state.get("category", "Unknown")}
- Root Cause: {state.get("root_cause", "Unknown")}""")

    # Denial details
    if state.get("denial_details"):
        denial = state["denial_details"]
        parts.append(f"""## Original Denial
- Reason: {denial.denial_reason or 'Not provided'}
- Details: {json.dumps(denial.decision_details) if denial.decision_details else 'Not provided'}""")

    # Service information for policy lookup
    if state.get("service_details"):
        service = state["service_details"]
        parts.append(f"""## Service Details (for policy lookup)
- CPT Codes: {service.cpt_codes}
- HCPCS Codes: {service.hcpcs_codes}
- Diagnosis Codes: {service.dx_codes}""")

    return "Analyze gaps and create evidence search plan:\n\n" + "\n\n".join(parts)


def build_evidence_gatherer_user_prompt(state: DenialEvaluatorState) -> str:
    """Build user prompt for the evidence gatherer agent."""
    parts = []

    # What we're looking for
    parts.append(f"""## Evidence Requirements
{chr(10).join(f"- {e}" for e in state.get("required_evidence", []))}""")

    # Search plan
    parts.append(f"""## Search Plan
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(state.get("search_plan", [])))}""")

    # Policy references to validate against
    if state.get("policy_references"):
        parts.append(f"""## Policy References
{chr(10).join(f"- {ref}" for ref in state["policy_references"])}""")

    # Context for searches
    if state.get("service_details"):
        service = state["service_details"]
        parts.append(f"""## Search Context
- CPT Codes: {service.cpt_codes}
- Diagnosis Codes: {service.dx_codes}
- Service Period: {service.service_start_date} to {service.service_end_date}""")

    if state.get("clinical_context"):
        clinical = state["clinical_context"]
        parts.append(f"""## Clinical Context
- Primary Diagnosis: {clinical.primary_diagnosis}
- Supporting Diagnoses: {clinical.supporting_diagnoses}
- Relevant History: {clinical.relevant_history}
- Prior Treatments: {clinical.prior_treatments}
- Clinical Notes: {clinical.clinical_notes}""")

    return "Gather evidence following the search plan:\n\n" + "\n\n".join(parts)


def build_reasoning_user_prompt(state: DenialEvaluatorState) -> str:
    """Build user prompt for the reasoning agent."""
    parts = []

    # Denial summary
    parts.append(f"""## Denial Summary
- Category: {state.get("category", "Unknown")}
- Root Cause: {state.get("root_cause", "Unknown")}""")

    if state.get("denial_details"):
        denial = state["denial_details"]
        parts.append(f"- Original Reason: {denial.denial_reason}")

    if state.get("cliniclinical_context"):
        parts.append(f"""## Clinical Context already shared with payer
- Relevant History: {state["clinical_context"].relevant_history}
- Prior Treatments: {state["clinical_context"].prior_treatments}
- Clinical Notes: {state["clinical_context"].clinical_notes}""")


    if state.get("documents_shared"):
        parts.append(f"""## Documents already shared with payer
{chr(10).join(f"{doc.document_id}- {doc.title}" for doc in state["documents_shared"])}""")

    # Evidence found
    if state.get("found_evidence"):
        evidence_items = []
        for e in state["found_evidence"]:
            evidence_items.append(f"  - [{e.evidence_type}] {e.fact} (Source: {e.source}, Relevance: {e.relevance})")
        parts.append(f"""## Evidence Found
{chr(10).join(evidence_items)}""")

    # Missing evidence
    if state.get("missing_evidence"):
        parts.append(f"""## Missing Evidence
{chr(10).join(f"- {m}" for m in state["missing_evidence"])}""")

    # Policy references
    if state.get("policy_references"):
        parts.append(f"""## Applicable Policy References
{chr(10).join(f"- {ref}" for ref in state["policy_references"])}""")

    # Service details for context
    if state.get("service_details"):
        service = state["service_details"]
        parts.append(f"""
## Service Information
- CPT Codes: {service.cpt_codes}
- HCPCS Codes: {service.hcpcs_codes}
- Diagnosis Codes (ICD-10): {service.dx_codes}
- Site of Service: {service.site_of_service}
- Requested Units: {service.requested_units}
- Service Period: {service.service_start_date} to {service.service_end_date}
- Urgency Level: {service.urgency_level}
""")

    return "Analyze evidence and recommend action:\n\n" + "\n\n".join(parts)
