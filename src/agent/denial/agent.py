"""Workflow for evaluating PA denial decisions."""

import json
from typing import Literal, Optional, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime


from .state import (
    DenialEvaluatorState,
    DenialDetails,
    GapAnalysis,
    Evidence,
    EvidenceGathering,
    Judgement,
    RecommendedAction,
    DenialCategorization,
    DenialEvaluationResult,
    REVISE_CATEGORIES
)
from .system_prompts import (
    CATEGORIZER_SYSTEM_PROMPT,
    GAP_ANALYSIS_SYSTEM_PROMPT,
    EVIDENCE_GATHERER_SYSTEM_PROMPT,
    REASONING_SYSTEM_PROMPT
)
from .user_prompts_builder import (
    build_categorizer_user_prompt,
    build_gap_analysis_user_prompt,
    build_evidence_gatherer_user_prompt,
    build_reasoning_user_prompt
)
from ...tools import (
    search_patient_documents,
    get_patient_health_record,
    get_procedure_details,
    get_drug_coverage_details,
    check_step_therapy_requirements,
    validate_codes,
    lookup_policy_criteria,
)

from ...models.core import ServiceInfo, ClinicalContext


def create_gap_analysis_agent(model_id) -> CompiledStateGraph:
    model = ChatOpenAI(model=model_id, timeout=20, max_retries=3)
    agent = create_agent(
        model=model,
        tools=[lookup_policy_criteria],
        system_prompt=GAP_ANALYSIS_SYSTEM_PROMPT,
        response_format=ProviderStrategy(GapAnalysis)
    )
    return agent

def create_evidence_gatherer_agent(model_id):
    model = ChatOpenAI(model=model_id, timeout=20, max_retries=3)
    agent = create_agent(
        model=model,
        tools=[
            get_patient_health_record,
            get_procedure_details,
            get_drug_coverage_details,
            check_step_therapy_requirements,
            validate_codes,
            search_patient_documents,
        ],
        system_prompt=EVIDENCE_GATHERER_SYSTEM_PROMPT,
        response_format=ProviderStrategy(EvidenceGathering),
    )
    return agent


def create_denial_evaluation_workflow(model_id: str = "gpt-4o-mini"):
    """Create the denial evaluator workflow"""
    
    # Initialize LLMs
    llm = ChatOpenAI(model="gpt-4o", timeout=20, max_retries=3)
    gap_analyst = create_gap_analysis_agent(model_id)
    evidence_gatherer = create_evidence_gatherer_agent(model_id)

    async def categorizer_node(state: DenialEvaluatorState) -> dict:
        """Categorize the denial decision."""

        user_message = build_categorizer_user_prompt(state)
        messages = [
            SystemMessage(content=CATEGORIZER_SYSTEM_PROMPT),
            HumanMessage(content=user_message)
        ]

        llm_with_structure_output = llm.with_structured_output(schema=DenialCategorization)
        response: DenialCategorization = await llm_with_structure_output.ainvoke(messages)

        if response.category in REVISE_CATEGORIES:
            return {
                "category": response.category,
                "root_cause": response.root_cause,
                "recommendation": RecommendedAction.REVISE_AND_RESUBMIT
            }

        return {
            "category": response.category,
            "root_cause": response.root_cause
        }

    async def gap_analyst_node(state: DenialEvaluatorState, runtime: Runtime) -> dict:

        user_message = build_gap_analysis_user_prompt(state)
        result = await gap_analyst.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            context=runtime.context
        )
        response: GapAnalysis = result["structured_response"]

        return {
            "required_evidence": response.required_evidence,
            "search_plan": response.search_plan,
            "policy_references": response.policy_references
        }

    async def evidence_gather_node(state: DenialEvaluatorState, runtime: Runtime) -> dict:

        user_message = build_evidence_gatherer_user_prompt(state)
        result = await evidence_gatherer.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            context=runtime.context
        )
        response: EvidenceGathering = result["structured_response"]

        return {
            "found_evidence": response.found_evidences,
            "missing_evidence": response.missing_evidence,
        }

    async def reasoning_node(state: DenialEvaluatorState) -> dict:
        print("inside reasoning_node")
        user_message = build_reasoning_user_prompt(state)
        messages = [
            SystemMessage(content=REASONING_SYSTEM_PROMPT),
            HumanMessage(content=user_message)
        ]
        llm_with_structure_output = llm.with_structured_output(schema=Judgement)
        response: Judgement = await llm_with_structure_output.ainvoke(messages)
        
        revision_count = state.get("revision_count", 0)
        print(response.confidence_score)
        if response.confidence_score < 0.7 and response.require_more_evidence and revision_count < 1:
            return {
                "required_evidence": response.require_more_evidence,
                "search_plan": response.search_plan,
                "need_revision": True,
                "revision_count": revision_count + 1
            }
        
        return {
            "judgement": response,
            "recommendation": response.recommendation,
            "need_revision": False,
        }

    def route_after_categorize(state: DenialEvaluatorState) -> Literal["gap_analyst", END]:
        if state.get("recommendation"):
            return END
        return "gap_analyst"

    def route_after_reasoning(state: DenialEvaluatorState) -> Literal["evidence_gatherer", END]:
        if state.get("need_revision", False):
            return "evidence_gatherer"
        return END
    

    workflow = StateGraph(DenialEvaluatorState)
    workflow.add_node("categorize", categorizer_node)
    workflow.add_node("gap_analyst", gap_analyst_node)
    workflow.add_node("evidence_gatherer", evidence_gather_node)
    workflow.add_node("reasoner", reasoning_node)
    
    workflow.set_entry_point("categorize")
    workflow.add_conditional_edges("categorize", route_after_categorize)
    workflow.add_edge("gap_analyst", "evidence_gatherer")
    workflow.add_edge("evidence_gatherer", "reasoner")
    workflow.add_conditional_edges("reasoner", route_after_reasoning)
    
    return workflow.compile()


_denial_evaluation_workflow = create_denial_evaluation_workflow()

async def evaluate_denial(
    patient_id: str,
    denial_reason: str,
    decision_details: Optional[Dict[str, Any]],
    pa_request_id: str,
    payer_id: str,
    plan_id: str,
    service_details: ServiceInfo,
    clinical_context: ClinicalContext,
) -> DenialEvaluationResult:
    """Evaluate a PA denial and recommend next steps."""
    
    denial_details = DenialDetails(
        denial_reason=denial_reason,
        decision_details=decision_details
    )
    
    initial_state : DenialEvaluatorState = {
        "denial_details": denial_details,
        "service_details": service_details,
        "clinical_context": clinical_context,
        "revision_count": 0
    }
    
    result = await _denial_evaluation_workflow.ainvoke(
        initial_state,
        config = RunnableConfig(recursion_limit=70),
        context={
                "patient_id": patient_id, 
                "pa_request_id": pa_request_id, 
                "payer_id": payer_id, 
                "plan_id": plan_id
        })

    judgement: Judgement = result.get("judgement")
    evidences: List[Evidence] = []
    if judgement:
        for citation in judgement.evidence_citations:
            try:
                evidences.append(result.get("found_evidence")[citation])
            except:
                continue


    return DenialEvaluationResult(
        recommendation=result.get("recommendation"),
        confidence_score=judgement.confidence_score if judgement else 1.0, #for only categorization case
        root_cause=result.get("root_cause"),
        evidences=evidences,
        appeal_strength_score=judgement.appeal_strength_score if judgement else 0,
        clinical_argument_summary=judgement.clinical_argument_summary if judgement else None,
        required_documentation=judgement.required_documentation if judgement else None,
        policy_references=result.get("policy_references", [])
    )


if __name__ == "__main__":
    import asyncio
    from ...intake_scenarios import get_intake
    from ..state import PAIntake

    intake = PAIntake(**(get_intake("PA-SCENARIO-C")))

    async def main():
        result = await evaluate_denial(
            patient_id=intake.patient_id,
            denial_reason="Medical necessity not established - duplicate imaging within 12 months without documented clinical change",
            decision_details={
                "prior_mri_date": "2024-08-15",
                "prior_mri_findings": "L4-L5 left paracentral disc herniation with L5 nerve root compression"
            },
            pa_request_id=intake.pa_request_id,
            payer_id="BCBS001",
            plan_id="PLAN001",
            service_details=intake.service_info,
            clinical_context=ClinicalContext(clinical_notes=intake.clinical_notes, primary_diagnosis="Intervertebral disc degeneration, lumbar region")
        )
        print(json.dumps(result.model_dump(), indent=2))

    asyncio.run(main())
