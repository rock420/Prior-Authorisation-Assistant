"""LangGraph agent for handling Requirement."""

from typing import Literal, List, Dict
import uuid
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Send
from langchain_core.runnables import RunnableConfig


from .state import (
    GathererState,
    RequirementAgentState,
    RequireItem,
    ParsedRequireItem,
    ParsedRequireItemList,
    RequireItemStatus,
    GathererResult,
    EvaluatorVerdict,
    RequireItemResult,
)
from ...tools import search_patient_documents, get_patient_health_record, get_procedure_details
from ...models.core import ServiceInfo, ClinicalContext


REQUIREMENT_HANDLER_TOOLS = [
    search_patient_documents,
    get_patient_health_record,
    get_procedure_details,
]


PARSER_SYSTEM_PROMPT = """You are an Requirement parser that converts requested information into structured items.

For each requested item, determine:
1. A clear concise description of what's being requested
2. The document type if it's a document request (clinical_note, lab_result, imaging_report, etc.)
3. Keywords that would help search for this information

Output a list of parsed Requirement items."""


GATHERER_SYSTEM_PROMPT = """You are a healthcare data gatherer agent responsible for finding information to respond to Requirement.

Your role is to:
1. Search for relevant documents and clinical information using the available tools
2. Gather comprehensive data that addresses the specific Requirement
3. Report what you found with confidence level

## IMPORTANT RULES
1. You must not invent clinical facts or coverage rules you cannot verify
2. Only use the data provided to make decision
3. Do not make assumptions beyond what the data shows
4. Only derive information from the data presented and always provide specific evidence

## Process
1. Analyze the Requirement item to understand what's being requested
2. Use appropriate tools to search for the information
3. Gather all relevant data that could satisfy the request
4. Report your findings with a summary and confidence score

{case_context}

Search for information to satisfy this Requirement request:
Requirement Item: {description}
Document Type: {document_type}
Keywords: {keywords}

Use the available tools to find relevant documents and information.

"""


EVALUATOR_SYSTEM_PROMPT = """You are a quality evaluator that determines if gathered data satisfies Requirement requests.

Your role is to:
1. Review what was requested in the Requirement item
2. Evaluate if the gathered data adequately addresses the request
3. Identify any major gaps in the information
4. Determine if human intervention is needed

## Evaluation Criteria

- Does the gathered data address what was requested?
- Is the information complete and current?
- Are there any major gaps that could cause the Requirement response to be rejected?
- Is any major additional information should be gathered?

## When to Require Human in the loop

- Document doesn't exist and needs to be created (e.g., letter of medical necessity)
- Information requires clinical judgment to compile
- Sensitive information that needs clinician review before submission
- Ambiguous request that needs clarification

{case_context}

## Requested Requirement: {requirement}

## Gathered Data: 
{gatherer_result}
"""


def get_case_context(state: GathererState) -> str:
    # Build context
    context_parts = []
    
    if state.get("service_details"):
        service = state.get("service_details")
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
        clinical = state.get("clinical_context")
        context_parts.append(f"""
## Clinical Context
- Primary Diagnosis: {clinical.primary_diagnosis}
- Supporting Diagnoses: {clinical.supporting_diagnoses}
- Relevant History: {clinical.relevant_history}
- Prior Treatments: {clinical.prior_treatments}
- Clinical Notes: {clinical.clinical_notes}
""")

    if context_parts:
        return "# Case Context:\n\n" + "\n".join(context_parts)
    return ""


def create_gatherer_subgraph(llm: ChatOpenAI):
    """Create the gatherer subgraph with isolated state per Require item."""
    
    async def gather_information_node(state: GathererState) -> dict:
        """Gatherer agent searches for information using tools."""
        parsed_require_item: ParsedRequireItem = state["parsed_require_item"]
        
        system_prompt = GATHERER_SYSTEM_PROMPT.format(
            case_context=get_case_context(state),
            description=parsed_require_item.description,
            document_type=parsed_require_item.document_type.value if parsed_require_item.document_type else "Not specified",
            keywords=", ".join(parsed_require_item.keywords) if parsed_require_item.keywords else "None"
        )

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        
        llm_with_tools = llm.bind_tools(REQUIREMENT_HANDLER_TOOLS)
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}
    
    tool_node = ToolNode(REQUIREMENT_HANDLER_TOOLS)
    
    async def gather_decision_node(state: GathererState) -> dict:
        """Gatherer produces structured result after searching."""
        parsed_require_item: ParsedRequireItem = state["parsed_require_item"]

        system_prompt = GATHERER_SYSTEM_PROMPT.format(
            case_context=get_case_context(state),
            description=parsed_require_item.description,
            document_type=parsed_require_item.document_type.value if parsed_require_item.document_type else "Not specified",
            keywords=", ".join(parsed_require_item.keywords) if parsed_require_item.keywords else "None"
        )
        
        decision_prompt = """Based on your search, provide a structured result for this Requirement item:

Provide:
- status: found, partially_found, or not_found
- found_documents: List of documents found (with document_id, title, type)
- found_information: Any relevant information found
- search_summary: Summary of what you searched for
- confidence: Your confidence in the findings (0.0-1.0)"""

        messages = [SystemMessage(content=system_prompt)] + state["messages"] + [HumanMessage(content=decision_prompt)]

        gatherer_structured_llm = llm.with_structured_output(GathererResult)
        result = await gatherer_structured_llm.ainvoke(messages)
        
        return {"gather_result": result}
    
    async def evaluator_node(state: GathererState) -> dict:
        """Evaluate if gathered data satisfies the Requirement request."""
        parsed_require_item: ParsedRequireItem = state["parsed_require_item"]
        gatherer_result: GathererResult = state["gather_result"]

        system_prompt = EVALUATOR_SYSTEM_PROMPT.format(
            case_context=get_case_context(state),
            requirement=parsed_require_item.original_request,
            gatherer_result=gatherer_result.model_dump_json(indent=2)
        )

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        evaluator_structured_llm = llm.with_structured_output(EvaluatorVerdict)
        verdict = await evaluator_structured_llm.ainvoke(messages)
                
        return {"evaluator_verdict": verdict}
    
    def route_after_gather(state: GathererState) -> Literal["tools", "gather_decision"]:
        """Route after gatherer - check if tools need to be called."""
        messages = state["messages"]
        if not messages:
            return "gather_decision"
        last_message = messages[-1]
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        return "gather_decision"
    
    # Build the subgraph
    subgraph = StateGraph(GathererState)
    
    subgraph.add_node("gather_information", gather_information_node)
    subgraph.add_node("tools", tool_node)
    subgraph.add_node("gather_decision", gather_decision_node)
    subgraph.add_node("evaluator", evaluator_node)
    
    subgraph.set_entry_point("gather_information")
    
    subgraph.add_conditional_edges(
        "gather_information",
        route_after_gather,
        {"tools": "tools", "gather_decision": "gather_decision"}
    )
    subgraph.add_edge("tools", "gather_information")
    subgraph.add_edge("gather_decision", "evaluator")
    subgraph.add_edge("evaluator", END)
    
    return subgraph.compile()


def create_requirement_handler_agent(model_id: str = "gpt-4o-mini"):
    """Create the Requirement handler LangGraph agent."""
    
    llm = ChatOpenAI(model=model_id)
    gatherer_subgraph = create_gatherer_subgraph(llm)
    
    # Node 1: Parse Requirement items
    async def parse_requirement_node(state: RequirementAgentState) -> dict:
        """Parse raw Requirement requests into structured items."""
        require_items: List[RequireItem] = state["require_items"]
        
        parse_prompt = f"""Parse these Requirement items into structured format:

Requested Items:
{chr(10).join(f"Item_Id: {item.item_id} - {item.requested_item}" for item in require_items)}
"""

        parser_llm = llm.with_structured_output(ParsedRequireItemList)
        parsed_require_items: ParsedRequireItemList = await parser_llm.ainvoke([
            SystemMessage(content=PARSER_SYSTEM_PROMPT),
            HumanMessage(content=parse_prompt)
        ])
        
        return {
            "parsed_require_items": parsed_require_items.items,
        }

    async def process_require_item_node(state: GathererState, config: RunnableConfig) -> dict:
        """Process a single Require item through the gatherer subgraph."""
        result = await gatherer_subgraph.ainvoke(state, config=config)
        
        parsed_require_item: ParsedRequireItem = state["parsed_require_item"]
        return {
            "gatherer_results": {parsed_require_item.item_id: result["gather_result"]},
            "evaluator_verdicts": {parsed_require_item.item_id: result["evaluator_verdict"]}
        }
    
    # Node 7: Output - compile final result
    async def output_node(state: RequirementAgentState) -> dict:
        """Compile final Requirement response."""
        parsed_require_items: List[ParsedRequireItem] = state["parsed_require_items"]
        gatherer_results: Dict[str, GathererResult] = state["gatherer_results"]
        evaluator_verdicts: Dict[str, EvaluatorVerdict] = state["evaluator_verdicts"]
        
        # Build item results
        item_results = []
        for item in parsed_require_items:
            gatherer = gatherer_results.get(item.item_id, None)
            verdict = evaluator_verdicts.get(item.item_id, None)
                        
            item_results.append(RequireItemResult(
                item_id=item.item_id,
                original_request=item.original_request,
                optional=item.optional,
                status=gatherer.status if gatherer else RequireItemStatus.NOT_FOUND,
                documents=gatherer.found_documents if gatherer else [],
                information=gatherer.found_information if gatherer else None,
                supporting_evidence=gatherer.supporting_evidence if gatherer else [],
                gaps=verdict.gaps if verdict else []
            ))

        return {
            "require_item_result": item_results,
            "processing_complete": True
        }
    
    # Routing logic
    def route_to_gather(state: RequirementAgentState):
        return [
            Send("process_requirement_item", {
                "parsed_require_item": item,
                "service_details": state["service_details"],
                "clinical_context": state["clinical_context"],
                "messages": []
            }) 
            for item in state["parsed_require_items"]
        ]
    
    # Build the graph
    workflow = StateGraph(RequirementAgentState)
    
    # Add nodes
    workflow.add_node("parse_requirement", parse_requirement_node)
    workflow.add_node("process_requirement_item", process_require_item_node)
    workflow.add_node("output", output_node)
    
    # Set entry point
    workflow.set_entry_point("parse_requirement")
    
    # Add edges
    workflow.add_conditional_edges("parse_requirement", route_to_gather, ["process_requirement_item"])
    workflow.add_edge("process_requirement_item", "output")
    workflow.add_edge("output", END)
    
    return workflow.compile()

_requirement_agent = create_requirement_handler_agent()

async def handle_requirements(
    patient_id: str,
    pa_request_id: str,
    payer_id: str,
    plan_id: str,
    require_items: List[RequireItem],
    service_details: ServiceInfo,
    clinical_context: ClinicalContext,
) -> List[RequireItemResult]:


    initial_state = {
        "require_items": require_items,
        "service_details": service_details,
        "clinical_context": clinical_context,
        "messages": [],
        "parsed_require_items": [],
        "require_item_result": [],
        "processing_complete": False,
    }
    
    result = await _requirement_agent.ainvoke(
        initial_state,
        config=RunnableConfig(recursion_limit=50),
        context={
            "patient_id": patient_id, 
            "pa_request_id": pa_request_id, 
            "payer_id": payer_id, 
            "plan_id": plan_id
        }
    )
    
    return result.get("require_item_result")
