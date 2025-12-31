from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, UTC

from ..models.core import ClinicalContext, PAWorkFlowStatus, PayerInfo, ServiceInfo, PARequest, ProviderInfo
from ..models.integration import AccessPurpose, PARequirement, PAStatusResponse, PAStatus, PatientDataRequest, PHICategory, UploadDocument
from ..models.hitl import HITLTask, TaskType, TaskPriority, TaskStatus
from ..models.document import DocumentType, DocumentMappingList, DocumentMetadata
from .state import PAIntake, PAAgentState
from ..integrations.document_service import document_search_tool
from ..integrations.ehr_service import get_patient_summary
from ..integrations.provider import get_provider_details, create_task_for_staff
from ..integrations.payer_service import check_coverage, is_pa_required, submit_pa, check_pa_status, upload_documents
from .denial import evaluate_denial, DenialEvaluationResult, RecommendedAction
from .denial.state import DenialCategory, Evidence
from .requirement import handle_requirements, RequireItem, RequireItemStatus, RequireItemResult
from ..pa_status_poller import track_submission
from ..hitl_task_poller import track_hitl_task
from .system_prompts import APPEAL_DRAFT_SYSTEM_PROMPT
from .user_prompts_builder import build_appeal_user_prompt


from langchain_openai import ChatOpenAI
from langgraph.errors import NodeInterrupt
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage

from uuid import uuid4
from pathlib import Path

appeal_draft_dir = Path(__file__).resolve().parent.parent.parent / "data/appeal"

model = ChatOpenAI(model="gpt-4o-mini", timeout=20, max_retries=3)
_memory: Optional[MemorySaver] = None

# Console output helper
def log_status(message: str, is_hitl: bool = False) -> None:
    """Print formatted status message to console."""
    prefix = "🔔 PA Agent:" if is_hitl else "🤖 PA Agent:"
    print(f"{prefix} {message}")

def get_memory() -> MemorySaver:
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory

async def intake_node(state: PAIntake) -> PAAgentState:
    log_status(f"Processing intake for patient {state.patient_name}...")
    clinical_context = ClinicalContext(
        primary_diagnosis=state.primary_diagnosis,
        secondary_diagnoses=state.secondary_diagnoses,
        clinical_notes=state.clinical_notes,
        supporting_documents=state.supporting_documents,
    )

    service_provider = get_provider_details(state.provider_id)
    log_status("Intake complete. Starting coverage verification...")

    return PAAgentState(
        pa_request_id=state.pa_request_id,
        clinical_context=clinical_context,
        patient_name=state.patient_name,
        patient_id=state.patient_id,
        service_info=state.service_info,
        additional_notes=state.additional_notes,
        workflow_status=PAWorkFlowStatus.INTAKE,
        clinician_id = state.submitted_by,
        provider_info=service_provider,
    )


async def determine_coverage(state: PAAgentState) -> PAAgentState:
    log_status("Verifying patient coverage and eligibility...")
    patient_id: str =  state.get("patient_id")
    pa_request_id: str = state.get("pa_request_id")
    
    limited_patient_summary = get_patient_summary(PatientDataRequest(
        patient_id=patient_id,
        categories=[PHICategory.COVERAGE],
        purpose=AccessPurpose.ELIGIBILITY_CHECK,
        requester_id="pa_agent_workflow",
        justification="Need coverage data for eligibility checking"
    ))

    
    coverage = check_coverage( 
        payer_id=limited_patient_summary.coverage["payer_id"],
        plan_id=limited_patient_summary.coverage["plan_id"],
        patient_id=patient_id
    )

    if coverage is not None:
        log_status(f"Coverage verified: {coverage.plan_details.get('plan_name')}")
        return {
            "payer_info" : PayerInfo(
                payer_id=coverage.plan_details.get("payer_id"),
                payer_name=coverage.plan_details.get("payer_name"),
                plan_id=coverage.plan_details.get("plan_id"),
                member_id=coverage.plan_details.get("member_id"),
                plan_name=coverage.plan_details.get("plan_name"),
                effective_date=coverage.plan_details.get("effective_date"),
                termination_date=coverage.plan_details.get("termination_date")
            ),
            "workflow_status": PAWorkFlowStatus.COVERAGE_DETERMINATON
    }
    return state

async def pa_requirement_discovery(state: PAAgentState) -> PAAgentState:
    log_status("Checking if prior authorization is required...")
    # Extract typed values from state dict
    payer_info: PayerInfo = state["payer_info"]
    service_info: ServiceInfo = state["service_info"]
    
    # Get payer information from coverage
    payer_id = payer_info.payer_id
    plan_id = payer_info.plan_id

    # Get service information
    cpt_codes = service_info.cpt_codes
    hcpcs_codes = service_info.hcpcs_codes
    diagnosis_codes = service_info.dx_codes
    site_of_service = service_info.site_of_service
    
    pa_requirement: PARequirement = is_pa_required(
        payer_id=payer_id, 
        plan_id=plan_id, 
        cpt_codes=cpt_codes,
        hcpcs_codes=hcpcs_codes,
        dx_codes=diagnosis_codes, 
        site_of_service=site_of_service
    )

    requirement_id: str = "REQUIREMENT-"+str(uuid4())
    require_items = []
    for index, item in enumerate(pa_requirement.required_documentation):
        require_items.append(
            RequireItem(
                item_id=requirement_id+"-"+str(index),
                requested_item=item
            )
        )

    if pa_requirement.required:
        log_status(f"PA required. Found {len(require_items)} documentation requirements.")
    else:
        log_status("PA not required for this service.")

    return {
        "is_pa_required": pa_requirement.required,
        "require_items": require_items,
        "workflow_status": PAWorkFlowStatus.ELIGIBILITY_DETERMINATION
    }

async def gather_pa_requirement(state: PAAgentState) -> PAAgentState:
    require_items: List[RequireItem] = state.get("require_items")
    log_status(f"Gathering {len(require_items)} required documents...")
    
    pa_request_id: str = state.get("pa_request_id")
    patient_id: str = state.get("patient_id")
    service_info: ServiceInfo = state.get("service_info")
    clinical_context: ClinicalContext = state.get("clinical_context")
    payer_info: PayerInfo = state.get("payer_info")
    provider_info: ProviderInfo = state.get("provider_info")
    
    requirement_result: List[RequireItemResult] = await handle_requirements(
        patient_id=patient_id,
        pa_request_id=pa_request_id,
        payer_id=payer_info.payer_id,
        plan_id=payer_info.plan_id,
        require_items=require_items,
        service_details=service_info,
        clinical_context=clinical_context,
    )

    found_count = sum(1 for r in requirement_result if r.status == RequireItemStatus.FOUND)
    log_status(f"Document gathering complete. Found {found_count}/{len(require_items)} requirements.")

    return {"requirement_result": requirement_result, "workflow_status": PAWorkFlowStatus.REQUIREMENT_COLLECTION}
 
async def submission(state: PAAgentState) -> PAAgentState:
    """
    Submit the PA request to the payer.
    Builds PARequest from state and calls submit_pa.
    """
    log_status("Submitting PA request to payer...")
    
    # Extract data from state
    pa_request_id: str = state.get("pa_request_id")
    patient_id: str = state["patient_id"]
    service_info: ServiceInfo = state["service_info"]
    clinical_context: ClinicalContext = state["clinical_context"]
    payer_info: PayerInfo = state["payer_info"]
    provider_info: ProviderInfo = state["provider_info"]
    
    # Update clinical context with collected documents
    clinical_context_with_docs = ClinicalContext(
        primary_diagnosis=clinical_context.primary_diagnosis,
        supporting_diagnoses=clinical_context.supporting_diagnoses,
        relevant_history=clinical_context.relevant_history,
        prior_treatments=clinical_context.prior_treatments,
        clinical_notes=clinical_context.clinical_notes,
    )
    
    # Build PARequest
    pa_request = PARequest(
        id=pa_request_id,
        patient_id=patient_id,
        requesting_provider=provider_info,
        service_details=service_info,
        clinical_context=clinical_context_with_docs,
        payer_info=payer_info,
    )
    
    # Submit to payer
    result = submit_pa(pa_request)
    
    if result.success:
        log_status(f"Submission successful! ID: {result.submission_id}")
        return {
            "submission_id": result.submission_id,
            "submission_timestamp": result.submission_timestamp,
            "workflow_status": PAWorkFlowStatus.SUBMISSION,
        }
    else:
        # Submission failed - create HITL task for retry
        log_status(f"Submission failed: {result.error_message}", is_hitl=True)
        clinician_id: str = state.get("clinician_id", "unknown")
        hitl_task = HITLTask(
            task_id="HITL-" + str(uuid4()),
            pa_request_id=pa_request_id,
            task_type=TaskType.TECHNICAL_ESCALATION,
            title="PA Submission Failed",
            description=f"Submission failed: {result.error_message}. Please review and retry.",
            assigned_to=clinician_id,
        )
        create_task_for_staff(hitl_task.task_type, hitl_task)
        return {
            "validation_errors": [result.error_message],
            "awaiting_clinician_input": True,
            "pending_hitl_task": hitl_task,
        }

async def tracking_node(state: PAAgentState) -> PAAgentState:
    pa_submission_id: str = state.get("submission_id")
    pa_request_id: str = state.get("pa_request_id")

    #check status
    status: PAStatusResponse = check_pa_status(pa_submission_id)

    if not status or status.status == PAStatus.PENDING:
        track_submission(pa_request_id, pa_submission_id)
        NodeInterrupt("PA status is still in pending")
    
    #Todo: save the status in PA_Status table

    return { "status": status}

async def approved_node(state: PAAgentState) -> PAAgentState:
    log_status("PA APPROVED! Authorization complete.")
    #notify approval
    return {"workflow_status": PAWorkFlowStatus.RESOLUTION}

async def denial_node(state: PAAgentState) -> PAAgentState:
    pa_status: PAStatusResponse = state.get("status")
    log_status(f"Analyzing denial reason: {pa_status.denial_reason}")
    payer_info: PayerInfo = state.get("payer_info")

    result : DenialEvaluationResult = await evaluate_denial(
        patient_id=state.get("patient_id"),
        pa_request_id=state.get("pa_request_id"),
        denial_reason=pa_status.denial_reason,
        decision_details=pa_status.decision_details,
        payer_id=payer_info.payer_id,
        plan_id=payer_info.plan_id,
        service_details=state.get("service_info"),
        clinical_context=state.get("clinical_context"),
        documents_shared=state.get("uploaded_documents")
    )

    if result.confidence_score<0.7:
        ##agent not able to conclude, create HITL task
        log_status("Need Human review: Unable to determine best action for this denial.", is_hitl=True)
        pa_request_id: str = state.get("pa_request_id")
        clinician_id: str = state.get("clinician_id")
        hitl_task = HITLTask(
            task_id="HITL-" + str(uuid4()),
            pa_request_id=pa_request_id,
            task_type=TaskType.AMBIGUOUS_RESPONSE,            
            title="Please review the denial decision",
            description = f"Agent is not able to conclude denial reason due to ambiguity or less context",
            context_data={"denial_reason": pa_status.denial_reason, "decision_details": pa_status.decision_details},
            assigned_to=clinician_id,
        )
        create_task_for_staff(hitl_task.task_type, hitl_task)
        return {
            "awaiting_clinician_input": True,
            "pending_hitl_task": hitl_task
        }
    
    log_status(f"Denial analysis complete. Recommendation: {result.recommendation.value.upper()}")
    return { "denial_evaluation": result, "workflow_status": PAWorkFlowStatus.DENIAL_EVALUATION}

async def revise_node(state: PAAgentState) -> PAAgentState:
    log_status("Preparing revised submission with additional documentation...")
    return {"workflow_status": PAWorkFlowStatus.REVISE}

async def appeal_node(state: PAAgentState) -> PAAgentState:
    """
    Check appeal readiness and draft an appeal letter using LLM with template.
    Creates Appeal object and HITL task for clinician approval.
    """
    log_status("Drafting appeal letter...")
    from ..models.core import Appeal
    from ..models.appeal import AppealLetterContent, build_appeal_letter
    
    # Extract state data
    pa_request_id: str = state.get("pa_request_id")
    patient_id: str = state.get("patient_id")
    patient_name: str = state.get("patient_name")
    denial_evaluation: DenialEvaluationResult = state.get("denial_evaluation")
    pa_status: PAStatusResponse = state.get("status")
    service_info: ServiceInfo = state.get("service_info")
    clinical_context: ClinicalContext = state.get("clinical_context")
    payer_info: PayerInfo = state.get("payer_info")
    provider_info: ProviderInfo = state.get("provider_info")
    clinician_id: str = state.get("clinician_id")
    
    # Build prompts
    user_prompt = build_appeal_user_prompt(
        denial_evaluation=denial_evaluation,
        pa_status=pa_status,
        service_info=service_info,
        clinical_context=clinical_context
    )
    
    structured_model = model.with_structured_output(AppealLetterContent)
    appeal_content: AppealLetterContent = await structured_model.ainvoke([
        SystemMessage(APPEAL_DRAFT_SYSTEM_PROMPT),
        HumanMessage(user_prompt)
    ])
    
    service_description = f"CPT: {', '.join(service_info.cpt_codes)} | DX: {', '.join(service_info.dx_codes)}"
    provider_addr = provider_info.address
    provider_address_str = f"{provider_addr.get('street', '')}, {provider_addr.get('city', '')}, {provider_addr.get('state', '')} {provider_addr.get('zip', '')}"

    # Build the complete letter from template
    draft_letter = build_appeal_letter(
        patient_name=patient_name,
        patient_id=patient_id,
        member_id=payer_info.member_id,
        pa_request_id=pa_request_id,
        denial_date=pa_status.status_date,
        denial_reason=pa_status.denial_reason,
        service_description=service_description,
        provider_name=provider_info.name,
        provider_organization=provider_info.organization,
        provider_npi=provider_info.npi,
        provider_phone=provider_info.phone,
        provider_address=provider_address_str,
        payer_name=payer_info.payer_name,
        payer_address="",  # Could be fetched from payer service
        content=appeal_content,
    )

    appeal_id = "APPEAL-"+str(uuid4())
    with open(appeal_draft_dir / f"{appeal_id}.txt", "x") as f:
        f.write(draft_letter)
    
    # Create Appeal object
    appeal = Appeal(
        appeal_id="APPEAL-" + str(uuid4()),
        original_pa_request_id=pa_request_id,
        denial_details={
            "denial_reason": pa_status.denial_reason,
            "decision_details": pa_status.decision_details,
            "root_cause": denial_evaluation.root_cause
        },
        appeal_type=denial_evaluation.recommendation.value,
        denial_category=denial_evaluation.root_cause,
        clinical_justification=appeal_content.clinical_justification,
        supporting_evidence=[e.fact for e in denial_evaluation.evidences],
        medical_literature=[],
        draft_id=appeal_id,
        required_approvals=["clinician", "medical_director"],
        approvals_received=[]
    )
    
    # Create HITL task for clinician review and approval
    hitl_task = HITLTask(
        task_id="HITL-" + str(uuid4()),
        pa_request_id=pa_request_id,
        task_type=TaskType.APPEAL_REVIEW,
        title="Review and Approve Appeal Letter",
        description=f"Please review the drafted appeal letter for PA denial. Denial reason: {pa_status.denial_reason}",
        context_data={
            "appeal": appeal.model_dump(),
            "required_documents": denial_evaluation.required_documentation,
            "appeal_strength_score": denial_evaluation.appeal_strength_score
        },
        assigned_to=clinician_id,
    )
    create_task_for_staff(hitl_task.task_type, hitl_task)
    
    log_status(f"Need Human review: Appeal letter drafted (strength score: {denial_evaluation.appeal_strength_score}/100). Please review and approve.", is_hitl=True)
    
    return {
        "workflow_status": PAWorkFlowStatus.APPEAL,
        "awaiting_clinician_input": True,
        "pending_hitl_task": hitl_task
    }



async def rfi_node(state: PAAgentState) -> PAAgentState:
    pa_status: PAStatusResponse = state.get("status")
    log_status(f"Payer requested additional information ({len(pa_status.rfi_details)} items)...")

    requirement_id: str = "REQUIREMENT-"+str(uuid4())
    require_items = []
    for index, item in enumerate(pa_status.rfi_details):
        require_items.append(
            RequireItem(
                item_id=requirement_id+"-"+str(index),
                requested_item=item
            )
        )
    
    #save the requiremnt in db

    return {"require_items": require_items}


async def validate_requirements(state: PAAgentState):
    log_status("Validating gathered requirements...")
    requirement_result: List[RequireItemResult] = state["requirement_result"]

    #Todo: consider verdicts
    item_requires_hitl = [item for item in requirement_result if item.status!=RequireItemStatus.FOUND and not item.optional]

    if item_requires_hitl:
        pa_request_id: str = state.get("pa_request_id")
        clinician_id: str = state["clinician_id"]
        item_description = []
        item_context = {}
        for current_item in item_requires_hitl:
            item_description.append(f""""
            Required information: {current_item.original_request}
            Related documents found: {current_item.documents}
            Related information found: {current_item.information}
            Gaps Identified: {', '.join(current_item.gaps)}
            """)
            item_context[current_item.item_id] = {
                "Required information": current_item.original_request,
                "state": current_item.status,
            }

        hitl_task = HITLTask(
            task_id="HITL-"+str(uuid4()),
            pa_request_id=pa_request_id,
            task_type=TaskType.REQUIRE_DOCUMENTS,
            title=f"Requires more documents or information",
            description=f"""Unable to automatically gather information for below requested information.

    {chr(10).join(item_description)}

    Please provide the required information or document.""",
            context_data=item_context,
            assigned_to=clinician_id
        )
        create_task_for_staff(hitl_task.task_type, hitl_task)

        log_status(f"Need Human review: Missing {len(item_requires_hitl)} required document(s). Please provide.", is_hitl=True)
        for item in item_requires_hitl:
            log_status(f"  → {item.original_request}", is_hitl=True)

        return {
            "awaiting_clinician_input": True,
            "pending_hitl_task": hitl_task,
            "workflow_status": PAWorkFlowStatus.REQUIREMENT_VALIDATION
        }
        ## make an entry to database

async def upload_require_documents(state:PAAgentState):
    log_status("Uploading supporting documents to payer...")
    requirement_result: List[RequireItemResult] = state.get("requirement_result")
    pa_submission_id: str = state.get("submission_id")

    documents: List[UploadDocument] = []
    for item in requirement_result:
        #update the database with the new documents
        documents += [UploadDocument(document_id=doc.document_id, title=doc.title) for doc in item.documents]
        if item.information:
            #if there is information, create a pdf out of it and upload the information
            pass
    
    upload_documents(submission_id=pa_submission_id, documents=documents)

    log_status(f"Uploaded {len(documents)} document(s).")
    return {"requirement_result":[], "require_items":[], "uploaded_documents": documents,"workflow_status": PAWorkFlowStatus.UPLOAD_REQUIREMENTS}

async def human_intervention(state: PAAgentState) -> PAAgentState:
    if state.get("awaiting_clinician_input"):
        pending_task: HITLTask = state.get("pending_hitl_task")
        if pending_task:
            track_hitl_task(pending_task)
        raise NodeInterrupt("Awaiting human intervention")
    return state


#### Routers

def check_pa_requirement(state: PAAgentState) -> Literal["gather_pa_requirement", "submission" ,END]:
    if not state["is_pa_required"]:
        return END
    elif not state["require_items"]:
        return "submission"
    else:
        return "gather_pa_requirement"

def route_after_requirement_validation(state: PAAgentState) -> Literal["human_intervention", "upload_requirements", "submission"]:
    "human_intervention" if state.get("awaiting_clinician_input") else "submission"
    if state.get("awaiting_clinician_input"):
        return "human_intervention"
    elif not state.get("submission_id"): #PA submission has not happened yet
        return "submission"
    else:
        return "upload_requirements"

def router_after_tracking(state: PAAgentState) -> Literal["approve", "denial", "rfi", END]:
    pa_status: PAStatusResponse = state.get("status")
    if pa_status.status == PAStatus.APPROVED:
        return "approve"
    elif pa_status.status == PAStatus.DENIED:
        return "denial"
    elif pa_status.status == PAStatus.RFI:
        return "rfi"
    return END

def route_after_denial(state: PAAgentState) -> Literal["appeal", "revise", "human_intervention", END]:
    if state.get("awaiting_clinician_input", False):
        return "human_intervention"
    
    denial_evaluation: DenialEvaluationResult = state.get("denial_evaluation")
    if denial_evaluation.recommendation == RecommendedAction.APPEAL:
        return "appeal"
    elif denial_evaluation.recommendation == RecommendedAction.REVISE_AND_RESUBMIT:
        return "revise"
    else:
        log_status("Final denial. No viable path to approval.")
        return END


def create_workflow() -> StateGraph:
    workflow = StateGraph(PAAgentState, input_schema=PAIntake)
    workflow.add_node("intake", intake_node)
    workflow.add_node("determine_coverage", determine_coverage)
    workflow.add_node("pa_requirement_discovery", pa_requirement_discovery)
    workflow.add_node("gather_pa_requirement", gather_pa_requirement)
    workflow.add_node("validate_requirements", validate_requirements)
    workflow.add_node("upload_requirements", upload_require_documents)
    workflow.add_node("submission", submission)

    workflow.add_node("tracking", tracking_node)
    workflow.add_node("approve", approved_node)
    workflow.add_node("denial", denial_node)
    workflow.add_node("rfi", rfi_node)
    workflow.add_node("appeal", appeal_node)
    workflow.add_node("revise", revise_node)

    workflow.add_node("human_intervention", human_intervention)
    

    workflow.set_entry_point("intake")
    workflow.add_edge("intake", "determine_coverage")
    workflow.add_edge("determine_coverage", "pa_requirement_discovery")
    workflow.add_conditional_edges("pa_requirement_discovery", check_pa_requirement)
    workflow.add_edge("gather_pa_requirement", "validate_requirements")
    workflow.add_conditional_edges("validate_requirements", route_after_requirement_validation)
    workflow.add_edge("submission", "upload_requirements")
    workflow.add_edge("upload_requirements", "tracking")

    workflow.add_conditional_edges("tracking", router_after_tracking)
    workflow.add_edge("rfi", "gather_pa_requirement")
    workflow.add_conditional_edges("denial", route_after_denial)
    workflow.add_edge("appeal", "human_intervention")
    workflow.add_edge("revise", END)
    workflow.add_edge("approve", END)
    
    return workflow.compile(checkpointer=get_memory())

