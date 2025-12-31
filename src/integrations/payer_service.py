import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import random

from ..models import (
    CoverageInfo, 
    PARequirement, 
    SubmissionResult, 
    PAStatusResponse, 
    PAStatus, 
    UploadResult, 
    UploadDocument,
    PARequest
)

# Load mock data
_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


def check_coverage(payer_id: str, plan_id: str, patient_id: str) -> Optional[CoverageInfo]:
    """
    Check patient coverage eligibility and plan metadata.
    
    Args:
        payer_id: The payer identifier
        plan_id: The plan identifier
        patient_id: The patient identifier
        
    Returns:
        CoverageInfo or None if not found
    """
    coverage_data = _load_json("coverage.json")
    
    if payer_id not in coverage_data:
        return None
    
    payer = coverage_data[payer_id]
    
    if plan_id not in payer.get("plans", {}):
        return None
    
    plan = payer["plans"][plan_id]
    
    if patient_id not in plan.get("members", {}):
        return None
    
    member = plan["members"][patient_id]
    
    return CoverageInfo(
        eligible=member.get("eligibility_status") == "active",
        plan_details={
            "payer_id": payer_id,
            "payer_name": payer["payer_name"],
            "plan_id": plan_id,
            "plan_name": plan["plan_name"],
            "plan_type": plan.get("plan_type"),
            "member_id": member.get("member_id"),
            "effective_date": member.get("effective_date"),
            "termination_date": member.get("termination_date"),
            "coverage_type": member.get("coverage_type")
        },
        benefit_information={},
        copay_info={
            "copay": member.get("copay"),
            "deductible": member.get("deductible"),
            "out_of_pocket_max": member.get("out_of_pocket_max")
        },
        prior_auth_history=[]
    )


def is_pa_required(
    payer_id: str,
    plan_id: str,
    cpt_codes: List[str],
    hcpcs_codes: List[str],
    dx_codes: List[str],
    site_of_service: str
) -> PARequirement:
    """
    Determine if prior authorization is required for the given service.
    
    Args:
        payer_id: The payer identifier
        plan_id: The plan identifier  
        cpt_codes: List of CPT procedure codes
        hcpcs_codes: List of HCPCS codes (including J-codes for drugs)
        dx_codes: List of ICD-10 diagnosis codes
        site_of_service: Where the service will be performed
        
    Returns:
        PARequirement indicating if PA is required and what documents are needed
    """
    pa_data = _load_json("pa_requirements.json")
    rules = pa_data.get("rules", [])
    default = pa_data.get("default_response", {})
    
    all_procedure_codes = set(cpt_codes + hcpcs_codes)
    
    # Find matching rule
    for rule in rules:
        # Check payer match
        if payer_id not in rule.get("payer_ids", []):
            continue
        
        # Check procedure code match (CPT or HCPCS)
        rule_cpt = set(rule.get("cpt_codes", []))
        rule_hcpcs = set(rule.get("hcpcs_codes", []))
        rule_all_codes = rule_cpt.union(rule_hcpcs)
        
        if not rule_all_codes.intersection(all_procedure_codes):
            continue
            
        # Check site of service match (if specified in rule)
        rule_sites = rule.get("sites_of_service", [])
        if rule_sites and site_of_service not in rule_sites:
            continue
            
        # Check diagnosis codes (if specified in rule)
        rule_dx = set(rule.get("dx_codes", []))
        if rule_dx and not rule_dx.intersection(dx_codes):
            continue
        
        # Found matching rule
        return PARequirement(
            required=rule.get("pa_required", False),
            reason=rule.get("notes", f"Matched rule: {rule.get('rule_id')}"),
            required_documentation=rule.get("required_documents", [])
        )
    
    # No matching rule, return default
    return PARequirement(
        required=default.get("pa_required", False),
        reason=default.get("notes", "No matching PA rule found"),
        required_documentation=default.get("required_documents", [])
    )


def _save_json(filename: str, data: dict) -> None:
    """Save data to JSON file."""
    with open(_DATA_DIR / filename, "w") as f:
        json.dump(data, f, indent=2, default=str)


def submit_pa(pa_request: PARequest) -> SubmissionResult:
    """
    Submit a prior authorization request to the payer.
    
    Args:
        pa_request: PARequest with all required submission data
        
    Returns:
        SubmissionResult with submission_id if successful
    """
    # Load current submissions
    submissions_data = _load_json("pa_submissions.json")
    
    # Generate submission ID
    submission_id = f"SUB{submissions_data['next_submission_id']:06d}"
    submissions_data["next_submission_id"] += 1
    
    # Simulate occasional submission failures (5% chance)
    if random.random() < 0.05:
        return SubmissionResult(
            success=False,
            submission_id=None,
            error_message="Payer system temporarily unavailable. Please retry."
        )
    
    # Validate required fields
    if not pa_request.service_details.cpt_codes:
        return SubmissionResult(
            success=False,
            submission_id=None,
            error_message="At least one CPT code is required"
        )
    
    if not pa_request.service_details.dx_codes:
        return SubmissionResult(
            success=False,
            submission_id=None,
            error_message="At least one diagnosis code is required"
        )
    
    # Determine initial status based on documentation completeness
    has_clinical_notes = bool(pa_request.clinical_context.clinical_notes)
    has_documents = len(pa_request.clinical_context.supporting_documents) > 0
    
    # Store submission
    submission_record = {
        "submission_id": submission_id,
        "pa_request_id": pa_request.id,
        "patient_id": pa_request.patient_id,
        "member_id": pa_request.payer_info.member_id,
        "payer_id": pa_request.payer_info.payer_id,
        "plan_id": pa_request.payer_info.plan_id,
        "provider_id": pa_request.requesting_provider.provider_id,
        "provider_npi": pa_request.requesting_provider.npi,
        "cpt_codes": pa_request.service_details.cpt_codes,
        "dx_codes": pa_request.service_details.dx_codes,
        "site_of_service": pa_request.service_details.site_of_service,
        "requested_units": pa_request.service_details.requested_units,
        "service_start_date": pa_request.service_details.service_start_date.isoformat(),
        "service_end_date": pa_request.service_details.service_end_date.isoformat(),
        "primary_diagnosis": pa_request.clinical_context.primary_diagnosis,
        "clinical_notes": pa_request.clinical_context.clinical_notes,
        "supporting_documents": pa_request.clinical_context.supporting_documents,
        "status": PAStatus.PENDING,
        "submitted_at": datetime.utcnow().isoformat(),
        "last_updated": datetime.utcnow().isoformat(),
    }
    
    submissions_data["submissions"][submission_id] = submission_record
    _save_json("pa_submissions.json", submissions_data)
    
    return SubmissionResult(
        success=True,
        submission_id=submission_id,
        submission_timestamp=datetime.utcnow()
    )


def check_pa_status(submission_id: str) -> Optional[PAStatusResponse]:
    """
    Check the status of a PA submission.
    
    Args:
        submission_id: The submission ID returned from submit_pa
        
    Returns:
        PAStatusResponse with current status, or None if not found
    """
    submissions_data = _load_json("pa_submissions.json")
    
    if submission_id not in submissions_data.get("submissions", {}):
        return None
    
    submission = submissions_data["submissions"][submission_id]
    current_status = submission["status"]
    
    return PAStatusResponse(
        status=current_status,
        status_date=datetime.fromisoformat(submission["last_updated"]),
        decision_details=submission.get("decision_details", {}),
        authorization_number=submission.get("authorization_number", None),
        denial_reason=submission.get("denial_reason", None),
        rfi_details=submission.get("rfi_details", [])
    )


def upload_documents(
    submission_id: str,
    documents: List[UploadDocument]
) -> UploadResult:
    """
    Upload additional documents to an existing PA submission.
    
    Args:
        submission_id: The submission ID to attach documents to
        documents: List of document objects to upload
        
    Returns:
        UploadResult with success status and details of uploaded/failed documents
    """
    # Load submissions
    submissions_data = _load_json("pa_submissions.json")
    
    # Verify submission exists
    if submission_id not in submissions_data.get("submissions", {}):
        return UploadResult(
            success=False,
            uploaded_documents=[],
            failed_documents=[{"error": f"Submission {submission_id} not found"}]
        )
    
    submission = submissions_data["submissions"][submission_id]
    
    # Check if submission is in a state that accepts documents
    if submission["status"] in ["approved", "denied"]:
        return UploadResult(
            success=False,
            uploaded_documents=[],
            failed_documents=[{
                "error": f"Cannot upload documents to submission with status: {submission['status']}"
            }]
        )
    
    uploaded_docs = []
    failed_docs = []
    
    for doc in documents:        
        # Add document to submission
        doc_record = {
            "document_id": doc.document_id,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        # Initialize supporting_documents if it doesn't exist or is not a list
        if not isinstance(submission.get("supporting_documents"), list):
            submission["supporting_documents"] = []
        
        ## fetch and upload docs
        submission["supporting_documents"].append(doc_record)
        uploaded_docs.append(doc.document_id)
    
    # Update submission
    submission["last_updated"] = datetime.utcnow().isoformat()
    
    _save_json("pa_submissions.json", submissions_data)
    
    return UploadResult(
        success=len(failed_docs) == 0,
        uploaded_documents=uploaded_docs,
        failed_documents=failed_docs
    )
