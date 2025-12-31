
import pytest
import os
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("OPENAI_API_KEY", "test-key-for-unit-tests")

from src.agent.workflow import (
    create_workflow,
    intake_node,
    determine_coverage,
    pa_requirement_discovery,
    gather_pa_requirement,
    validate_requirements,
    submission,
    tracking_node,
    denial_node,
    check_pa_requirement,
    route_after_denial,
    router_after_tracking,
)
from src.agent.state import PAIntake, PAAgentState
from src.agent.denial.state import (
    DenialCategory,
    RecommendedAction,
    DenialEvaluationResult,
    Evidence,
)
from src.agent.requirement.state import (
    RequireItem,
    RequireItemResult,
    RequireItemStatus,
)
from src.models.core import (
    ServiceInfo,
    ClinicalContext,
    PayerInfo,
    ProviderInfo,
    PAWorkFlowStatus,
    UrgencyLevel,
)
from src.models.integration import (
    PAStatus,
    PAStatusResponse,
    PARequirement,
    CoverageInfo,
    SubmissionResult,
)
from src.models.hitl import HITLTask, TaskType, TaskStatus


@pytest.fixture
def sample_intake() -> PAIntake:
    """Standard PA intake for MRI lumbar spine."""
    return PAIntake(
        pa_request_id=f"PA-TEST-{uuid4().hex[:8]}",
        patient_name="Test Patient",
        patient_id="PAT001",
        provider_id="PROV001",
        submitted_by="PROV001",
        primary_diagnosis="M54.5",
        secondary_diagnoses=["M54.16"],
        service_info=ServiceInfo(
            cpt_codes=["72148"],
            hcpcs_codes=[],
            dx_codes=["M54.5", "M54.16"],
            site_of_service="Outpatient Hospital",
            requested_units=1,
            service_start_date=datetime.now(UTC) + timedelta(days=7),
            service_end_date=datetime.now(UTC) + timedelta(days=7),
            urgency_level=UrgencyLevel.ROUTINE,
        ),
        clinical_notes=["Patient has chronic low back pain"],
        additional_notes=None,
    )


@pytest.fixture
def sample_payer_info() -> PayerInfo:
    return PayerInfo(
        payer_id="BCBS001",
        plan_id="PLAN001",
        plan_name="BCBS PPO",
        member_id="MEM123456",
        effective_date=datetime(2024, 1, 1),
        termination_date=None,
    )


@pytest.fixture
def sample_provider_info() -> ProviderInfo:
    return ProviderInfo(
        provider_id="PROV001",
        npi="1234567890",
        name="Dr. Test Provider",
        organization="Test Medical Center",
        phone="555-123-4567",
        email="test@medical.com",
        address={"street": "123 Medical Dr", "city": "Test City", "state": "CA", "zip_code": "90210"},
        license_number="MD12345",
    )


@pytest.fixture
def approved_status() -> PAStatusResponse:
    return PAStatusResponse(
        status=PAStatus.APPROVED,
        status_date=datetime.now(UTC),
        authorization_number="AUTH123456",
    )


@pytest.fixture
def denied_status() -> PAStatusResponse:
    return PAStatusResponse(
        status=PAStatus.DENIED,
        status_date=datetime.now(UTC),
        denial_reason="Medical necessity not established",
        decision_details={"reason_code": "MN001"},
    )


@pytest.fixture
def rfi_status() -> PAStatusResponse:
    return PAStatusResponse(
        status=PAStatus.RFI,
        status_date=datetime.now(UTC),
        rfi_details=["Recent lab results", "Physical therapy notes"],
    )

class TestHappyPath:
    """Tests for successful PA approval flow."""

    @pytest.mark.asyncio
    async def test_1_intake_transforms_to_agent_state(self, sample_intake):
        """Test 1: Intake node correctly transforms PAIntake to PAAgentState."""
        with patch("src.agent.workflow.get_provider_details") as mock_provider:
            mock_provider.return_value = ProviderInfo(
                provider_id="PROV001",
                npi="1234567890",
                name="Dr. Test",
                organization="Test Org",
                phone="555-123-4567",
                address={"street": "123 St", "city": "City", "state": "CA", "zip_code": "90210"},
                license_number="MD123",
            )
            
            result = await intake_node(sample_intake)
            
            assert result["pa_request_id"] == sample_intake.pa_request_id
            assert result["patient_id"] == sample_intake.patient_id
            assert result["workflow_status"] == PAWorkFlowStatus.INTAKE
            assert result["clinical_context"].primary_diagnosis == sample_intake.primary_diagnosis

    @pytest.mark.asyncio
    async def test_2_coverage_determination_success(self, sample_intake, sample_payer_info):
        """Test 2: Coverage determination retrieves and sets payer info."""
        state = {
            "pa_request_id": sample_intake.pa_request_id,
            "patient_id": sample_intake.patient_id,
        }
        
        mock_coverage = CoverageInfo(
            eligible=True,
            plan_details={
                "payer_id": "BCBS001",
                "plan_id": "PLAN001",
                "member_id": "MEM123",
                "plan_name": "BCBS PPO",
                "effective_date": "2024-01-01",
                "termination_date": None,
            },
        )
        
        with patch("src.agent.workflow.get_patient_summary") as mock_summary, \
             patch("src.agent.workflow.check_coverage") as mock_check:
            mock_summary.return_value = MagicMock(coverage={"payer_id": "BCBS001", "plan_id": "PLAN001"})
            mock_check.return_value = mock_coverage
            
            result = await determine_coverage(state)
            
            assert result["payer_info"].payer_id == "BCBS001"
            assert result["workflow_status"] == PAWorkFlowStatus.COVERAGE_DETERMINATON

    @pytest.mark.asyncio
    async def test_3_pa_not_required_ends_workflow(self, sample_payer_info):
        """Test 3: When PA is not required, workflow routes to END."""
        state = {
            "is_pa_required": False,
            "require_items": [],
        }
        
        result = check_pa_requirement(state)
        
        # LangGraph uses "__end__" as the END node identifier
        assert result == "__end__"

class TestRequirementGathering:
    """Tests for requirement discovery and gathering."""

    @pytest.mark.asyncio
    async def test_4_pa_requirement_discovery(self, sample_payer_info):
        """Test 4: PA requirement discovery identifies required documentation."""
        state = {
            "payer_info": sample_payer_info,
            "service_info": ServiceInfo(
                cpt_codes=["72148"],
                hcpcs_codes=[],
                dx_codes=["M54.5"],
                site_of_service="Outpatient",
                requested_units=1,
                service_start_date=datetime.now(UTC) + timedelta(days=7),
                service_end_date=datetime.now(UTC) + timedelta(days=7),
            ),
        }
        
        mock_requirement = PARequirement(
            required=True,
            reason="MRI requires PA",
            required_documentation=["Clinical notes", "Prior imaging"],
        )
        
        with patch("src.agent.workflow.is_pa_required") as mock_pa:
            mock_pa.return_value = mock_requirement
            
            result = await pa_requirement_discovery(state)
            
            assert result["is_pa_required"] is True
            assert len(result["require_items"]) == 2
            assert result["workflow_status"] == PAWorkFlowStatus.ELIGIBILITY_DETERMINATION

    @pytest.mark.asyncio
    async def test_5_requirement_validation_creates_hitl_for_gaps(self):
        """Test 5: Missing required documents trigger HITL task creation."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "clinician_id": "PROV001",
            "requirement_result": [
                RequireItemResult(
                    item_id="REQ-001",
                    original_request="Clinical notes",
                    optional=False,
                    status=RequireItemStatus.NOT_FOUND,
                    documents=[],
                    information=None,
                    supporting_evidence=[],
                    gaps=["No clinical notes found"],
                ),
            ],
        }
        
        with patch("src.agent.workflow.create_task_for_staff") as mock_task:
            result = await validate_requirements(state)
            
            assert result["awaiting_clinician_input"] is True
            assert result["pending_hitl_task"] is not None
            assert result["pending_hitl_task"].task_type == TaskType.REQUIRE_DOCUMENTS
            mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_6_optional_missing_docs_dont_block(self):
        """Test 6: Optional missing documents don't create HITL tasks."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "clinician_id": "PROV001",
            "requirement_result": [
                RequireItemResult(
                    item_id="REQ-001",
                    original_request="Optional imaging",
                    optional=True,
                    status=RequireItemStatus.NOT_FOUND,
                    documents=[],
                    information=None,
                    supporting_evidence=[],
                    gaps=["Not found"],
                ),
            ],
        }
        
        result = await validate_requirements(state)
        
        # Should not create HITL task for optional items
        assert result is None or result.get("awaiting_clinician_input") is not True

class TestDenialHandling:
    """Tests for denial evaluation and routing."""

    @pytest.mark.asyncio
    async def test_7_denial_routes_to_appeal(self, denied_status, sample_payer_info):
        """Test 7: High-confidence appeal recommendation routes to appeal node."""
        denial_eval = DenialEvaluationResult(
            root_cause="Insufficient documentation of failed conservative therapy",
            recommendation=RecommendedAction.APPEAL,
            confidence_score=0.85,
            evidences=[Evidence(source="EHR", evidence_type="treatment_history", fact="PT completed", relevance=0.9)],
            appeal_strength_score=75,
            clinical_argument_summary="Strong case for appeal",
            required_documentation=["Letter of medical necessity"],
            policy_references=["Policy 4.1.2"],
        )
        
        state = {
            "awaiting_clinician_input": False,
            "denial_evaluation": denial_eval,
        }
        
        result = route_after_denial(state)
        
        assert result == "appeal"

    @pytest.mark.asyncio
    async def test_8_denial_routes_to_revise(self, denied_status):
        """Test 8: Revise recommendation routes to revise node."""
        denial_eval = DenialEvaluationResult(
            root_cause="Missing documentation",
            recommendation=RecommendedAction.REVISE_AND_RESUBMIT,
            confidence_score=0.9,
            evidences=[],
            appeal_strength_score=0,
            clinical_argument_summary=None,
            required_documentation=["Updated clinical notes"],
            policy_references=[],
        )
        
        state = {
            "awaiting_clinician_input": False,
            "denial_evaluation": denial_eval,
        }
        
        result = route_after_denial(state)
        
        assert result == "revise"

    @pytest.mark.asyncio
    async def test_9_low_confidence_denial_creates_hitl(self, denied_status, sample_payer_info):
        """Test 9: Low confidence denial evaluation creates HITL task."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "patient_id": "PAT001",
            "clinician_id": "PROV001",
            "status": denied_status,
            "payer_info": sample_payer_info,
            "service_info": ServiceInfo(
                cpt_codes=["72148"],
                hcpcs_codes=[],
                dx_codes=["M54.5"],
                site_of_service="Outpatient",
                requested_units=1,
                service_start_date=datetime.now(UTC) + timedelta(days=7),
                service_end_date=datetime.now(UTC) + timedelta(days=7),
            ),
            "clinical_context": ClinicalContext(primary_diagnosis="M54.5"),
        }
        
        low_confidence_result = DenialEvaluationResult(
            root_cause="Unclear denial reason",
            recommendation=RecommendedAction.APPEAL,
            confidence_score=0.5,  # Below 0.7 threshold
            evidences=[],
            appeal_strength_score=40,
            clinical_argument_summary=None,
            required_documentation=[],
            policy_references=[],
        )
        
        with patch("src.agent.workflow.evaluate_denial", new_callable=AsyncMock) as mock_eval, \
             patch("src.agent.workflow.create_task_for_staff") as mock_task:
            mock_eval.return_value = low_confidence_result
            
            result = await denial_node(state)
            
            assert result["awaiting_clinician_input"] is True
            assert result["pending_hitl_task"].task_type == TaskType.AMBIGUOUS_RESPONSE

class TestRFIProcessing:
    """Tests for Request for Information handling."""

    @pytest.mark.asyncio
    async def test_10_rfi_creates_requirement_items(self, rfi_status):
        """Test 10: RFI response creates new requirement items."""
        state = {"status": rfi_status}
        
        from src.agent.workflow import rfi_node
        result = await rfi_node(state)
        
        assert len(result["require_items"]) == 2
        assert any("lab" in item.requested_item.lower() for item in result["require_items"])

    def test_11_tracking_routes_to_rfi(self, rfi_status):
        """Test 11: RFI status routes to rfi node."""
        state = {"status": rfi_status}
        
        result = router_after_tracking(state)
        
        assert result == "rfi"


class TestSubmission:
    """Tests for PA submission handling."""

    @pytest.mark.asyncio
    async def test_12_successful_submission(self, sample_payer_info, sample_provider_info):
        """Test 12: Successful submission sets submission_id and status."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "patient_id": "PAT001",
            "service_info": ServiceInfo(
                cpt_codes=["72148"],
                hcpcs_codes=[],
                dx_codes=["M54.5"],
                site_of_service="Outpatient",
                requested_units=1,
                service_start_date=datetime.now(UTC) + timedelta(days=7),
                service_end_date=datetime.now(UTC) + timedelta(days=7),
            ),
            "clinical_context": ClinicalContext(primary_diagnosis="M54.5"),
            "payer_info": sample_payer_info,
            "provider_info": sample_provider_info,
        }
        
        mock_result = SubmissionResult(
            success=True,
            submission_id="SUB000001",
            submission_timestamp=datetime.now(UTC),
        )
        
        with patch("src.agent.workflow.submit_pa") as mock_submit:
            mock_submit.return_value = mock_result
            
            result = await submission(state)
            
            assert result["submission_id"] == "SUB000001"
            assert result["workflow_status"] == PAWorkFlowStatus.SUBMISSION

    @pytest.mark.asyncio
    async def test_13_failed_submission_creates_hitl(self, sample_payer_info, sample_provider_info):
        """Test 13: Failed submission creates technical escalation HITL task."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "patient_id": "PAT001",
            "clinician_id": "PROV001",
            "service_info": ServiceInfo(
                cpt_codes=["72148"],
                hcpcs_codes=[],
                dx_codes=["M54.5"],
                site_of_service="Outpatient",
                requested_units=1,
                service_start_date=datetime.now(UTC) + timedelta(days=7),
                service_end_date=datetime.now(UTC) + timedelta(days=7),
            ),
            "clinical_context": ClinicalContext(primary_diagnosis="M54.5"),
            "payer_info": sample_payer_info,
            "provider_info": sample_provider_info,
        }
        
        mock_result = SubmissionResult(
            success=False,
            submission_id=None,
            error_message="Payer system unavailable",
        )
        
        with patch("src.agent.workflow.submit_pa") as mock_submit, \
             patch("src.agent.workflow.create_task_for_staff") as mock_task:
            mock_submit.return_value = mock_result
            
            result = await submission(state)
            
            assert result["awaiting_clinician_input"] is True
            assert result["pending_hitl_task"].task_type == TaskType.TECHNICAL_ESCALATION
            assert "unavailable" in result["validation_errors"][0]

class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_14_tracking_routes_correctly_for_all_statuses(self):
        """Test 14: Tracking node routes correctly for all PA statuses."""
        test_cases = [
            (PAStatus.APPROVED, "approve"),
            (PAStatus.DENIED, "denial"),
            (PAStatus.RFI, "rfi"),
        ]
        
        for status, expected_route in test_cases:
            state = {
                "status": PAStatusResponse(
                    status=status,
                    status_date=datetime.now(UTC),
                )
            }
            result = router_after_tracking(state)
            assert result == expected_route, f"Expected {expected_route} for {status}, got {result}"

    @pytest.mark.asyncio
    async def test_15_coverage_not_found_returns_unchanged_state(self):
        """Test 15: Missing coverage returns state unchanged (graceful handling)."""
        state = {
            "pa_request_id": "PA-TEST-001",
            "patient_id": "PAT_UNKNOWN",
        }
        
        with patch("src.agent.workflow.get_patient_summary") as mock_summary, \
             patch("src.agent.workflow.check_coverage") as mock_check:
            mock_summary.return_value = MagicMock(coverage={"payer_id": "UNKNOWN", "plan_id": "UNKNOWN"})
            mock_check.return_value = None  # No coverage found
            
            result = await determine_coverage(state)
            
            # Should return original state when coverage not found
            assert result == state
