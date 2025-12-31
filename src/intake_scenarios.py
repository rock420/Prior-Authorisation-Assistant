"""
Intake data for the three PA workflow test scenarios.

Scenario A: MRI Lumbar Spine (PAT003) - Likely routine approval
Scenario B: Biologic/Humira (PAT004) - Step therapy risk, HITL required
Scenario C: Denial Appeal (PAT005) - Appeal workflow

"""

from datetime import datetime, timedelta, UTC
from uuid import uuid4

from .models.core import ServiceInfo



INTAKES = {
    "PA-SCENARIO-A": {
        "pa_request_id": "PA-SCENARIO-A",
        "patient_name": "Robert Thompson",
        "patient_id": "PAT003",
        "provider_id": "PROV001",
        "submitted_by": "PROV001",
        "service_info": ServiceInfo(
            cpt_codes=["72148"],  # MRI lumbar spine without contrast
            hcpcs_codes=[],
            dx_codes=["M54.5", "M54.16"],  # Low back pain, lumbar radiculopathy
            site_of_service="Outpatient Hospital",
            requested_units=1,
            service_start_date=datetime.now(UTC) + timedelta(days=3),
            service_end_date=datetime.now(UTC) + timedelta(days=3),
            urgency_level="routine"
        ),
        "primary_diagnosis": "Low back pain with left L5 radiculopathy",
        "secondary_diagnoses": [
            "Radiculopathy, lumbar region",
            "Other chronic pain"
        ],
        "clinical_notes": [
            "58 y/o male with low back pain x 2 months, now with radiating pain to left leg.",
            "Completed 12 sessions of physical therapy over 6 weeks with partial improvement.",
            "Failed NSAID therapy (Naproxen 500mg BID x 6 weeks) and muscle relaxants.",
            "New neurological deficits: Left L5 dermatomal numbness, EHL weakness 4/5, positive SLR.",
            "MRI indicated to evaluate for disc herniation causing nerve root compression."
        ]
    },
    "PA-SCENARIO-B": {
        "pa_request_id": "PA-SCENARIO-B",
        "patient_name": "Jennifer Martinez",
        "patient_id": "PAT004",
        "provider_id": "PROV002",
        "submitted_by": "PROV002",
        "service_info": ServiceInfo(
            cpt_codes=["J0129"],  # Adalimumab injection
            hcpcs_codes=["J0129"],
            dx_codes=["M05.79", "M06.09"],  # Seropositive RA, Seronegative RA
            site_of_service="Home Self-Administration",
            requested_units=26,  # 1 year supply (every 2 weeks)
            service_start_date=datetime.now(UTC) + timedelta(days=7),
            service_end_date=datetime.now(UTC) + timedelta(days=365),
            urgency_level="routine"
        ),
        "primary_diagnosis": "Rheumatoid arthritis with rheumatoid factor, multiple sites",
        "secondary_diagnoses": [
            "Rheumatoid arthritis without rheumatoid factor, multiple sites"
        ],
        "clinical_notes": [],
    },
    "PA-SCENARIO-C": {
        "pa_request_id": "PA-SCENARIO-C",
        "patient_name": "Michael Anderson",
        "patient_id": "PAT005",
        "provider_id": "PROV005",
        "submitted_by": "PROV005",
        "service_info": ServiceInfo(
            cpt_codes=["72148"],  # MRI lumbar spine without contrast
            hcpcs_codes=[],
            dx_codes=["M54.5", "M51.16", "M54.16"],  # Low back pain, disc degeneration, radiculopathy
            site_of_service="Outpatient Hospital",
            requested_units=1,
            service_start_date=datetime.now(UTC) + timedelta(days=5),
            service_end_date=datetime.now(UTC) + timedelta(days=5),
            urgency_level="routine"
        ),
        "primary_diagnosis": "Intervertebral disc degeneration, lumbar region",
        "secondary_diagnoses": [
            "Low back pain",
            "Radiculopathy, lumbar region"
        ],
        "clinical_notes": [
            "54 y/o male with known L4-L5 disc herniation (MRI 08/15/2024).",
            "Had lumbar epidural steroid injection on 09/15/2024 with initial 60% improvement.",
            "Symptoms have returned over past 2 weeks - left leg pain now 6/10.",
        ],
    }

}

"""
Additional context for Scenario C denial reason

{
    "denial_reason": "Medical necessity not established - duplicate imaging within 12 months without documented clinical change",
    "denial_code": "D201",
    "decision_details": {
        "prior_mri_date": "2024-08-15",
        "prior_mri_findings": "L4-L5 left paracentral disc herniation with L5 nerve root compression"
    }
}
"""

def get_intake(intake_id: str) -> dict:
    """Get intake by ID."""
    return INTAKES.get(intake_id, None)