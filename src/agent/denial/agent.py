"""LangGraph agent for evaluating PA denial decisions."""

import json
from typing import Literal, Optional, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableConfig


from .state import (
    DenialEvaluatorState,
    EvaluationResult,
    DenialDetails,
    DenialCategory,
    JudgeVerdict,
    DenialEvaluationResult
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


DENIAL_EVALUATOR_TOOLS = [
    get_patient_health_record,
    get_procedure_details,
    get_drug_coverage_details,
    check_step_therapy_requirements,
    validate_codes,
    lookup_policy_criteria,
    search_patient_documents,
]

EVALUATOR_SYSTEM_PROMPT = f"""You are a healthcare prior authorization denial evaluator agent.

Your role is to:
1. Gather relevant data using the available tools and root causing the denial reason
2. Analyze the denial reason against patient records, procedure details, and payer policies
3. Identify evidence that supports or contradicts the denial
4. Make a decision on denial category and recommended action with clear justification

## IMPORTANT RULES
1. You must not invent clinical facts or coverage rules you cannot verify
2. Only use the data provided to make decision
3. Do not make assumptions beyond what the data shows
4. When in doubt, gather more information before deciding
5. Always provide specific evidence for your claims
7. If you cannot make a confident decision or no enough data, indicate uncertainty and recommend next steps
8. Don't invoke the tool repeatedly with same kind of input 


## Denial Categories
Classify the denial into: {", ".join([d.value for d in DenialCategory])}

## Recommended Actions
- appeal: Strong case for overturning through formal appeal (use when evidence contradicts denial)
- revise_and_resubmit: Fix issues and submit new PA request (use when documentation is missing but obtainable)
- final_denial: No viable path to approval (use only when denial is clearly valid)

## Process
1. Gather all relevant data using tools
2. Analyze evidence for and against the denial
3. Finally when your evaluation is done and you have reached to a conclusion , Provide your decision in this format:

DECISION:
- denial_category: [category]
- recommended_action: [action]
- confidence: [0.0-1.0]

JUSTIFICATION:
[Detailed reasoning with specific evidence from gathered data]

SUPPORTING_EVIDENCE:
[MANDATORY - List actual evidence/citation supporting your decision/justification]

AMBIGOUS_EVIDENCE:
[List actual evidence/citation that contradicts your justification or you not able to make sense]

REQUIRED_NEXT_STEPS:
[Specific actions needed]

4. If there is not much details or documents to supports or contradicts the denial, only provide the denial_category for the denial reason
- denial_category: [category]
- confidence: [0.0-1.0]
- NOT_ENOUGH_DATA_FOUND
"""


JUDGE_SYSTEM_PROMPT = """You are a healthcare quality assurance judge reviewing prior authorization denial evaluation decisions.

Your role is to:
1. Review the evaluator's decision and justification alongside supporting/contradicting evidence
2. Verify the reasoning is sound and supported by the gathered data
3. Check for logical gaps or missed considerations
4. Either APPROVE the decision or send it back with SUGGESTIONS

## Review Criteria
- Is the denial category correctly identified?
- Is the recommended action appropriate given the evidence?
- Is the justification well-supported by the citations/evidence?
- Is all the data used for coming to the decision grounded to tool response without any hallucination?
- Are there any contradictions or gaps in reasoning?

Response with your verdict of APPROVED/REVISION alongside justification and confidence. Also provide suggestions for REVISION.
"""


OUTPUT_SYSTEM_PROMPT = """You are responsible for producing the final structured output for a pre-authorisation denial evaluation.

Take the approved evaluation decision and format it as a structured response.
"""


def create_denial_evaluator_agent(model_id: str = "gpt-4o-mini"):
    """Create the denial evaluator LangGraph agent with evaluator, judge, and output nodes."""
    
    # Initialize LLMs
    llm = ChatOpenAI(model=model_id)
    
    async def evaluator_node(state: DenialEvaluatorState) -> dict:
        """Evaluator agent that gathers data and makes initial decision."""
        messages = state["messages"]
        messages = [SystemMessage(content=EVALUATOR_SYSTEM_PROMPT)] + messages
        
        # If we have judge feedback, add it to context
        if state.get("judge_verdict"):
            feedback_msg = HumanMessage(content=f"""
The judge has reviewed your previous decision and requests revision:

{state['judge_verdict'].suggestions}

Please reconsider your analysis and provide an updated decision.""")
            messages = messages + [feedback_msg]
        
        llm_with_tools = llm.bind_tools(DENIAL_EVALUATOR_TOOLS)
        response = await llm_with_tools.ainvoke(messages)
        
        # Check if response contains a decision (no more tool calls needed)
        has_decision = "DECISION:" in response.content if hasattr(response, 'content') else False
        
        return {
            "messages": [response],
            "evaluator_decision": response.content if has_decision else None
        }
    
    # Tool node with result printing
    _tool_node = ToolNode(DENIAL_EVALUATOR_TOOLS)
    
    async def tool_node(state: DenialEvaluatorState) -> dict:
        """Execute tools and print results."""
        result = await _tool_node.ainvoke(state)
        # Print tool results
        # for msg in result.get("messages", []):
        #     if isinstance(msg, ToolMessage):
        #         print_tool_result(msg)
        return { **result, "tool_call_count": state.get("tool_call_count", 0) + 1 }
    
    # Judge
    async def judge_node(state: DenialEvaluatorState) -> dict:
        """Judge reviews the evaluator's decision."""

        messages = state["messages"]
        messages = [SystemMessage(content=JUDGE_SYSTEM_PROMPT)] + messages
        
        llm_with_structure_output = llm.with_structured_output(schema=JudgeVerdict)
        response : JudgeVerdict = await llm_with_structure_output.ainvoke(messages)
        
        return {
            "judge_verdict": response,
            "revision_count": state.get("revision_count", 0) + 1,
            "tool_call_count": 0
        }
    
    # Node 3: Output formatter
    async def output_node(state: DenialEvaluatorState) -> dict:
        """Format the final structured output."""

        # Output the structured JSON response."""
        evaluator_decision = state.get("evaluator_decision", "")
        #messages = state["messages"]
        messages = [
            SystemMessage(content=OUTPUT_SYSTEM_PROMPT),
            AIMessage(content=evaluator_decision)
        ]
        
        llm_with_structure_output = llm.with_structured_output(schema=EvaluationResult)
        response : EvaluationResult = await llm_with_structure_output.ainvoke(messages)
        
        return {
            "evaluation_result": response,
        }
    
    def route_after_evaluator(state: DenialEvaluatorState) -> Literal["tools", "judge"]:
        """Route after evaluator: to tools if tool calls, to judge if decision made."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If has tool calls, go to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        # If decision made, go to judge
        return "judge"
    
    def route_after_judge(state: DenialEvaluatorState) -> Literal["evaluator", "output", END]:
        """Route after judge: back to evaluator if revise, to output if approved."""
        # Limit revisions to prevent infinite loops
        if state.get("revision_count", 0) >= 2:
            return "output" if state.get("evaluator_decision") else END
        
        if state.get("judge_verdict") and state.get("judge_verdict").verdict == "APPROVED":
            return "output"
        
        return "evaluator"
    

    workflow = StateGraph(DenialEvaluatorState)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("judge", judge_node)
    workflow.add_node("output", output_node)
    
    # Set entry point
    workflow.set_entry_point("evaluator")
    
    # Add edges
    workflow.add_conditional_edges("evaluator", route_after_evaluator)
    workflow.add_conditional_edges("tools", lambda state: "evaluator" if state.get("tool_call_count", 0)<10 else "judge")
    workflow.add_conditional_edges("judge", route_after_judge)
    workflow.add_edge("output", END)
    
    return workflow.compile()


def get_case_context(state: DenialEvaluatorState) -> str:
    # Build context
    context_parts = []

    if state.get("denial_details"):
        denial = state["denial_details"]
        context_parts.append(f"""
## Denial Information
- Denial Reason: {denial.denial_reason or 'Not provided'}
- Decision Details: {denial.decision_details or 'Not provided'}
""")
        
    if state.get("service_details"):
        service = state["service_details"]
        context_parts.append(f"""
## Service Information
- CPT Codes: {service.cpt_codes}
- HCPCS Codes: {service.hcpcs_codes}
- Diagnosis Codes (ICD-10): {service.dx_codes}
- Site of Service: {service.site_of_service}
- Requested Units: {service.requested_units}
- Service Period: {service.service_start_date} to {service.service_end_date}
- Urgency Level: {service.urgency_level}
""")
        
    if state.get("clinical_context"):
        clinical = state["clinical_context"]
        context_parts.append(f"""
## Clinical Context
- Primary Diagnosis: {clinical.primary_diagnosis}
- Supporting Diagnoses: {clinical.supporting_diagnoses}
- Relevant History: {clinical.relevant_history}
- Prior Treatments: {clinical.prior_treatments}
- Clinical Notes: {clinical.clinical_notes}
""")

    if context_parts:
        return "\n\n# Evaluate this PA denial:\n\n" + "\n".join(context_parts)
    return ""


_denial_evaluator_agent = create_denial_evaluator_agent()

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
        "patient_id": patient_id,
        "denial_details": denial_details,
        "service_details": service_details,
        "clinical_context": clinical_context,
        "revision_count": 0
    }
    initial_state["messages"] = [HumanMessage(content=get_case_context(initial_state))]
    
    result = await _denial_evaluator_agent.ainvoke(
        initial_state,
        config = RunnableConfig(recursion_limit=50),
        context={
                "patient_id": patient_id, 
                "pa_request_id": pa_request_id, 
                "payer_id": payer_id, 
                "plan_id": plan_id
        })
    return DenialEvaluationResult(
        evaluation_result=result.get("evaluation_result", None),
        judge_verdict=result.get("judge_verdict", None),
        revision_count=result.get("revision_count", 0),
    )