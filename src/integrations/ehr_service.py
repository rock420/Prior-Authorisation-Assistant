"""Patient tools with purpose-based PHI access control."""

import json
from pathlib import Path
from typing import Optional, Dict, Any, Set, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from ..models.integration import PatientSummary, PHICategory, PatientDataRequest, AccessPurpose
from ..compliance.audit_logger import audit_logger

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> dict:
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


def _filter_by_purpose(
    patient_data: dict, 
    allowed_categories: Set[PHICategory]
) -> dict:
    """Filter patient data to only include allowed PHI categories."""
    filtered = {"patient_id": patient_data.get("patient_id", "")}
    
    if PHICategory.IDENTIFIERS in allowed_categories:
        filtered["demographics"] = patient_data.get("demographics", {})
    else:
        filtered["demographics"] = {}
    
    if PHICategory.CLINICAL in allowed_categories:
        filtered["problem_list"] = patient_data.get("problem_list", [])
        filtered["failed_therapies"] = patient_data.get("failed_therapies", [])
        filtered["conservative_therapy_history"] = patient_data.get("conservative_therapy_history", [])
    else:
        filtered["problem_list"] = []
        filtered["failed_therapies"] = []
    
    if PHICategory.TREATMENT in allowed_categories:
        filtered["medications"] = patient_data.get("medications", [])
    else:
        filtered["medications"] = []
    
    if PHICategory.ENCOUNTERS in allowed_categories:
        filtered["recent_visits"] = patient_data.get("recent_visits", [])
    else:
        filtered["recent_visits"] = []

    if PHICategory.COVERAGE in allowed_categories:
        filtered["coverage"] = patient_data.get("coverage", {})
    else:
        filtered["coverage"] = {}
    
    return filtered


def get_patient_summary(request: PatientDataRequest) -> Optional[PatientSummary]:
    """
    Get patient summary with purpose-based PHI filtering.
    
    Args:
        request: PatientDataRequest with patient_id, purpose, requester, and justification
        
    Returns:
        PatientSummary filtered to minimum necessary PHI, or None if not found
    """
    # Log access attempt BEFORE fetching data    
    audit_logger.log_phi_access(
        resource_type="patient",
        resource_id=request.patient_id,
        justification=request.justification,
        details={
            "purpose": request.purpose.value,
            "phi_categories": [c.value for c in request.categories],
        },
        user_id=request.requester_id
    )
    
    patients = _load_json("patients.json")
    
    if request.patient_id not in patients:
        return None
    
    patient = patients[request.patient_id]
    patient["patient_id"] = request.patient_id
    
    # Filter to minimum necessary PHI
    filtered = _filter_by_purpose(patient, set(request.categories))
    
    return PatientSummary(
        patient_id=request.patient_id,
        demographics=filtered["demographics"],
        active_problems=[p["description"] for p in filtered["problem_list"]] if filtered["problem_list"] else [],
        medications=filtered["medications"],
        recent_visits=filtered["recent_visits"],
        coverage=filtered["coverage"],
        allergies=[],
        last_updated=datetime.utcnow()
    )
