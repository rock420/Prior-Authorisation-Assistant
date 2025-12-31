
from typing import List
from .state import GathererState, ParsedRequireItem, GathererResult, RequireItem
from ...models.core import ServiceInfo, ClinicalContext


def build_case_context(state: GathererState) -> str:
    """Build case context section for prompts."""
    parts = []

    if state.get("service_details"):
        service = state["service_details"]
        parts.append(f"""## Service Information
- CPT Codes: {service.cpt_codes}
- HCPCS Codes: {service.hcpcs_codes}
- Diagnosis Codes (ICD-10): {service.dx_codes}
- Site of Service: {service.site_of_service}
- Requested Units: {service.requested_units}
- Service Period: {service.service_start_date} to {service.service_end_date}
- Urgency Level: {service.urgency_level}""")

    if state.get("clinical_context"):
        clinical = state["clinical_context"]
        parts.append(f"""## Clinical Context
- Primary Diagnosis: {clinical.primary_diagnosis}
- Supporting Diagnoses: {clinical.supporting_diagnoses}
- Relevant History: {clinical.relevant_history}
- Prior Treatments: {clinical.prior_treatments}
- Clinical Notes: {clinical.clinical_notes}""")

    if parts:
        return "# Case Context\n\n" + "\n\n".join(parts)
    return ""


def build_parser_user_prompt(require_items: List[RequireItem]) -> str:
    items_text = chr(10).join(
        f"- Item ID: {item.item_id} | Request: {item.requested_item}"
        for item in require_items
    )
    return f"""Parse these payer requirement items into structured format:

## Requested Items
{items_text}

"""


def build_gatherer_user_prompt(state: GathererState) -> str:
    parsed_item: ParsedRequireItem = state["parsed_require_item"]
    
    parts = [build_case_context(state)]
    
    doc_type = parsed_item.document_type.value if parsed_item.document_type else "Not specified"
    keywords = ", ".join(parsed_item.keywords) if parsed_item.keywords else "None"
    
    parts.append(f"""## Requirement to Satisfy
- Original Request: {parsed_item.original_request}
- Description: {parsed_item.description}
- Document Type: {doc_type}
- Search Keywords: {keywords}
- Optional: {parsed_item.optional}""")

    return "Search for information to satisfy this requirement:\n\n" + "\n\n".join(parts)


def build_evaluator_user_prompt(
    state: GathererState,
    gatherer_result: GathererResult
) -> str:
    """Build user prompt for the evaluator agent."""
    parsed_item: ParsedRequireItem = state["parsed_require_item"]
    
    parts = [build_case_context(state)]
    
    parts.append(f"""## Original Requirement
{parsed_item.original_request}""")

    # Format gathered data
    docs_text = "None found"
    if gatherer_result.found_documents:
        docs_text = chr(10).join(
            f"  - {doc.title} ({doc.document_type})" 
            for doc in gatherer_result.found_documents
        )
    
    evidence_text = "None"
    if gatherer_result.supporting_evidence:
        evidence_text = chr(10).join(f"  - {e}" for e in gatherer_result.supporting_evidence)

    parts.append(f"""## Gathered Data
- Status: {gatherer_result.status.value}
- Confidence: {gatherer_result.confidence}
- Search Summary: {gatherer_result.search_summary}

### Documents Found
{docs_text}

### Information Found
{gatherer_result.found_information or "None"}

### Supporting Evidence
{evidence_text}""")

    return "Evaluate if the gathered data satisfies the requirement:\n\n" + "\n\n".join(parts)
