"""Unit tests for PA Healthcare Agent data models."""

import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from models import (
    PARequest,
    ServiceInfo,
    ClinicalContext,
    PayerInfo,
    ProviderInfo,
    AuditEntry,
    UrgencyLevel,
    PAWorkFlowStatus,
)


class TestServiceInfo:
    """Test ServiceInfo model validation and functionality."""

    def test_valid_service_info_creation(self, sample_service_info):
        """Test creating a valid ServiceInfo instance."""
        assert sample_service_info.cpt_codes == ["72148"]
        assert sample_service_info.dx_codes == ["M54.5"]
        assert sample_service_info.urgency_level == UrgencyLevel.ROUTINE
        assert sample_service_info.requested_units == 1

    def test_service_info_code_validation(self):
        """Test that empty codes are rejected."""
        with pytest.raises(ValidationError):
            ServiceInfo(
                cpt_codes=[""],  # Empty code should fail
                dx_codes=["M54.5"],
                site_of_service="outpatient",
                requested_units=1,
                service_start_date=datetime.utcnow(),
                service_end_date=datetime.utcnow()
            )

    def test_service_info_units_validation(self):
        """Test that requested_units must be positive."""
        with pytest.raises(ValidationError):
            ServiceInfo(
                cpt_codes=["72148"],
                dx_codes=["M54.5"],
                site_of_service="outpatient",
                requested_units=0,  # Should be > 0
                service_start_date=datetime.utcnow(),
                service_end_date=datetime.utcnow()
            )


class TestClinicalContext:
    """Test ClinicalContext model validation and functionality."""

    def test_valid_clinical_context_creation(self, sample_clinical_context):
        """Test creating a valid ClinicalContext instance."""
        assert sample_clinical_context.primary_diagnosis == "M54.5"
        assert len(sample_clinical_context.supporting_diagnoses) == 1
        assert len(sample_clinical_context.prior_treatments) == 2

    def test_empty_primary_diagnosis_rejected(self):
        """Test that empty primary diagnosis is rejected."""
        with pytest.raises(ValidationError):
            ClinicalContext(primary_diagnosis="")

    def test_whitespace_primary_diagnosis_cleaned(self):
        """Test that whitespace in primary diagnosis is cleaned."""
        context = ClinicalContext(primary_diagnosis="  M54.5  ")
        assert context.primary_diagnosis == "M54.5"


class TestPayerInfo:
    """Test PayerInfo model validation and functionality."""

    def test_valid_payer_info_creation(self, sample_payer_info):
        """Test creating a valid PayerInfo instance."""
        assert sample_payer_info.payer_id == "BCBS_001"
        assert sample_payer_info.plan_name == "Blue Cross Blue Shield PPO Standard"
        assert sample_payer_info.termination_date is None

    def test_termination_date_validation(self):
        """Test that termination date must be after effective date."""
        effective_date = datetime(2024, 1, 1)
        
        with pytest.raises(ValidationError):
            PayerInfo(
                payer_id="TEST_001",
                plan_id="TEST_PLAN",
                plan_name="Test Plan",
                member_id="123456",
                effective_date=effective_date,
                termination_date=effective_date - timedelta(days=1)  # Before effective date
            )


class TestProviderInfo:
    """Test ProviderInfo model validation and functionality."""

    def test_valid_provider_info_creation(self, sample_provider_info):
        """Test creating a valid ProviderInfo instance."""
        assert sample_provider_info.provider_id == "PROV_001"
        assert sample_provider_info.npi == "1234567890"
        assert sample_provider_info.name == "Dr. John Smith"
        assert sample_provider_info.organization == "City Medical Center"

    def test_npi_validation(self):
        """Test NPI validation requires exactly 10 digits."""
        with pytest.raises(ValidationError, match="NPI must be exactly 10 digits"):
            ProviderInfo(
                provider_id="PROV_001",
                npi="123456789",  # Only 9 digits
                name="Dr. Test",
                organization="Test Clinic",
                phone="555-123-4567",
                address={
                    "street": "123 Test St",
                    "city": "Test City",
                    "state": "CA",
                    "zip_code": "90210"
                },
                license_number="MD12345"
            )

    def test_phone_validation(self):
        """Test phone number validation requires 10 digits."""
        with pytest.raises(ValidationError, match="Phone number must contain exactly 10 digits"):
            ProviderInfo(
                provider_id="PROV_001",
                npi="1234567890",
                name="Dr. Test",
                organization="Test Clinic",
                phone="555-123-456",  # Only 9 digits
                address={
                    "street": "123 Test St",
                    "city": "Test City",
                    "state": "CA",
                    "zip_code": "90210"
                },
                license_number="MD12345"
            )

    def test_address_validation(self):
        """Test address validation requires all fields."""
        with pytest.raises(ValidationError, match="Address missing required fields"):
            ProviderInfo(
                provider_id="PROV_001",
                npi="1234567890",
                name="Dr. Test",
                organization="Test Clinic",
                phone="555-123-4567",
                address={
                    "street": "123 Test St",
                    "city": "Test City",
                    # Missing state and zip_code
                },
                license_number="MD12345"
            )


class TestAuditEntry:
    """Test AuditEntry model validation and functionality."""

    def test_valid_audit_entry_creation(self):
        """Test creating a valid AuditEntry instance."""
        entry = AuditEntry(
            user_id="user123",
            action_type="data_access",
            resource_type="patient_record",
            resource_id="PT_12345"
        )
        assert entry.user_id == "user123"
        assert entry.phi_accessed is False
        assert entry.justification is None

    def test_phi_access_requires_justification(self):
        """Test that PHI access requires justification."""
        with pytest.raises(ValidationError):
            AuditEntry(
                user_id="user123",
                action_type="data_access",
                resource_type="patient_record",
                resource_id="PT_12345",
                phi_accessed=True  # No justification provided
            )

    def test_phi_access_with_justification(self):
        """Test that PHI access works with justification."""
        entry = AuditEntry(
            user_id="user123",
            action_type="data_access",
            resource_type="patient_record",
            resource_id="PT_12345",
            phi_accessed=True,
            justification="Required for PA submission"
        )
        assert entry.phi_accessed is True
        assert entry.justification == "Required for PA submission"


class TestPARequest:
    """Test PARequest model validation and functionality."""

    def test_valid_pa_request_creation(self, sample_pa_request):
        """Test creating a valid PARequest instance."""
        assert sample_pa_request.id == "PA_2024_001"
        assert sample_pa_request.status == PAWorkFlowStatus.INTAKE
        assert len(sample_pa_request.audit_trail) == 0
        assert sample_pa_request.submission_id is None
        assert isinstance(sample_pa_request.requesting_provider, ProviderInfo)
        assert sample_pa_request.requesting_provider.name == "Dr. John Smith"

    def test_add_audit_entry(self, sample_pa_request):
        """Test adding audit entries to PA request."""
        original_updated_at = sample_pa_request.updated_at
        
        sample_pa_request.add_audit_entry(
            user_id="user123",
            action_type="status_change",
            resource_type="pa_request",
            resource_id=sample_pa_request.id,
            details={"old_status": "intake", "new_status": "validation"}
        )
        
        assert len(sample_pa_request.audit_trail) == 1
        assert sample_pa_request.audit_trail[0].user_id == "user123"
        assert sample_pa_request.audit_trail[0].action_type == "status_change"
        assert sample_pa_request.updated_at > original_updated_at

    def test_add_phi_audit_entry(self, sample_pa_request):
        """Test adding PHI access audit entry."""
        sample_pa_request.add_audit_entry(
            user_id="user123",
            action_type="phi_access",
            resource_type="patient_record",
            resource_id="PT_12345",
            phi_accessed=True,
            justification="Required for clinical review"
        )
        
        assert len(sample_pa_request.audit_trail) == 1
        entry = sample_pa_request.audit_trail[0]
        assert entry.phi_accessed is True
        assert entry.justification == "Required for clinical review"
