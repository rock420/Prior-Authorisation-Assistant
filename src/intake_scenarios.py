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
        "clinical_notes": [
            "45 y/o female with seropositive rheumatoid arthritis diagnosed 8 months ago.",
            "Presenting with bilateral hand and wrist joint pain, morning stiffness lasting >1 hour daily.",
            "Physical exam: Synovitis in MCP joints 2-4 bilaterally, PIP joints with tenderness and swelling.",
            "Labs: RF positive (85 IU/mL), Anti-CCP positive (>250 U/mL), CRP elevated at 2.8 mg/dL, ESR 42 mm/hr.",
            "DAS28-CRP score: 5.2 indicating high disease activity.",
            "Provider recommends biologic therapy due to high disease activity and poor quality of life."
        ],
    },
    "PA-SCENARIO-C": {
        "pa_request_id": "PA-SCENARIO-C",
        "patient_name": "Michael Anderson",
        "patient_id": "PAT005",
        "provider_id": "PROV005",
        "submitted_by": "PROV005",
        "service_info": ServiceInfo(
            cpt_codes=["62322"],  # Lumbar epidural steroid injection
            hcpcs_codes=[],
            dx_codes=["M54.5", "M54.16", "M54.41"],
            site_of_service="Ambulatory Surgical Center",
            requested_units=1,
            service_start_date=datetime.now(UTC) + timedelta(days=5),
            service_end_date=datetime.now(UTC) + timedelta(days=5),
            urgency_level="routine"
        ),
        "primary_diagnosis": "Lumbar radiculopathy with documented disc herniation",
        "secondary_diagnoses": [
            "Low back pain",
            "Lumbago with sciatica, left side"
        ],
        "clinical_notes": [
            "52 y/o male with MRI-confirmed L4-L5 disc herniation compressing left L5 nerve root.",
            "Conservative treatment completed: 8 weeks physical therapy, NSAIDs (Meloxicam 15mg daily x 6 weeks), Gabapentin 300mg TID x 4 weeks.",
            "Pain persists at 7/10 with left leg radicular symptoms despite conservative management.",
            "Neurological exam: Left L5 dermatomal sensory deficit, EHL weakness 4/5, positive straight leg raise at 40 degrees.",
            "Patient has not had any prior epidural steroid injections - this is first ESI request.",
            "Requesting transforaminal epidural steroid injection at L4-L5 level for pain management.",
        ],
    }

}

"""
Additional context for Scenario C denial reason

{
    "denial_reason": "Step therapy requirement not met - patient must trial and fail conservative treatments before interventional procedures",
    "denial_code": "D205",
    "decision_details": {
        "payer_rationale": "Epidural steroid injection requires documentation of failed conservative therapy including physical therapy and oral medications. No documentation of conservative treatment attempts found in submitted records.",
        "policy_reference": "ESI-2024-001 Section 4.2",
        "required_documentation": "Physical therapy records, medication trial documentation"
    }
}
"""

def get_intake(intake_id: str) -> dict:
    """Get intake by ID."""
    return INTAKES.get(intake_id, None)
