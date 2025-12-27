"""Pytest configuration and fixtures for PA Healthcare Agent tests."""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any
from models import (
    PARequest,
    ServiceInfo,
    ClinicalContext,
    PayerInfo,
    ProviderInfo,
    UrgencyLevel,
    PAWorkFlowStatus,
)


@pytest.fixture
def sample_service_info() -> ServiceInfo:
    """Create a sample ServiceInfo for testing."""
    return ServiceInfo(
        cpt_codes=["72148"],  # MRI lumbar spine
        hcpcs_codes=[],
        dx_codes=["M54.5"],  # Low back pain
        site_of_service="outpatient",
        requested_units=1,
        service_start_date=datetime.utcnow() + timedelta(days=7),
        service_end_date=datetime.utcnow() + timedelta(days=7),
        urgency_level=UrgencyLevel.ROUTINE
    )


@pytest.fixture
def sample_clinical_context() -> ClinicalContext:
    """Create a sample ClinicalContext for testing."""
    return ClinicalContext(
        primary_diagnosis="M54.5",  # ICD-10 code for low back pain
        supporting_diagnoses=["M54.16"],
        relevant_history=["6 weeks of conservative therapy", "Physical therapy completed"],
        prior_treatments=[
            {"treatment": "NSAIDs", "duration": "4 weeks", "outcome": "minimal improvement"},
            {"treatment": "Physical therapy", "duration": "6 weeks", "outcome": "partial improvement"}
        ],
        clinical_notes=["Patient reports persistent pain despite conservative treatment"],
        supporting_documents=["pt_notes_2024_01.pdf", "imaging_xray_2024_01.pdf"]
    )


@pytest.fixture
def sample_payer_info() -> PayerInfo:
    """Create a sample PayerInfo for testing."""
    return PayerInfo(
        payer_id="BCBS_001",
        plan_id="PPO_STANDARD",
        plan_name="Blue Cross Blue Shield PPO Standard",
        member_id="123456789",
        effective_date=datetime(2024, 1, 1),
        termination_date=None
    )


@pytest.fixture
def sample_provider_info() -> ProviderInfo:
    """Create a sample ProviderInfo for testing."""
    return ProviderInfo(
        provider_id="PROV_001",
        npi="1234567890",
        name="Dr. John Smith",
        organization="City Medical Center",
        phone="555-123-4567",
        email="dr.smith@citymedical.com",
        address={
            "street": "123 Medical Drive",
            "city": "Healthcare City",
            "state": "CA",
            "zip_code": "90210"
        },
        license_number="MD12345"
    )


@pytest.fixture
def sample_pa_request(
    sample_service_info: ServiceInfo,
    sample_clinical_context: ClinicalContext,
    sample_payer_info: PayerInfo,
    sample_provider_info: ProviderInfo
) -> PARequest:
    """Create a sample PARequest for testing."""
    return PARequest(
        id="PA_2024_001",
        patient_id="PT_12345",
        requesting_provider=sample_provider_info,
        service_details=sample_service_info,
        clinical_context=sample_clinical_context,
        payer_info=sample_payer_info,
        status=PAWorkFlowStatus.INTAKE
    )
