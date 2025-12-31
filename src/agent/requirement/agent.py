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
from .system_prompts import (
    PARSER_SYSTEM_PROMPT,
    GATHERER_SYSTEM_PROMPT,
    GATHERER_DECISION_PROMPT,
    EVALUATOR_SYSTEM_PROMPT,
)
from .user_prompts_builder import (
    build_parser_user_prompt,
    build_gatherer_user_prompt,
    build_evaluator_user_prompt,
)
from ...tools import search_patient_documents, get_patient_health_record, get_procedure_details
from ...models.core import ServiceInfo, ClinicalContext


# Console output helper
def log_requirement(message: str) -> None:
    """Print formatted status message for requirement gathering."""
    print(f"   ├─ Requirement Gathering Agent: {message}")


REQUIREMENT_HANDLER_TOOLS = [
    search_patient_documents,
    get_patient_health_record,
    get_procedure_details,
]


def create_gatherer_subgraph(llm: ChatOpenAI):
    """Create the gatherer subgraph with isolated state per Require item."""
    
    async def gather_information_node(state: GathererState) -> dict:
        """Gatherer agent searches for information using tools."""
        parsed_require_item: ParsedRequireItem = state["parsed_require_item"]
        log_requirement(f"Searching for: {parsed_require_item.original_request[:50]}...")
        
        user_prompt = build_gatherer_user_prompt(state)
        messages = [
            SystemMessage(content=GATHERER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ] + state["messages"]
        
        llm_with_tools = llm.bind_tools(REQUIREMENT_HANDLER_TOOLS)
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}
    
    tool_node = ToolNode(REQUIREMENT_HANDLER_TOOLS)
    
    async def gather_decision_node(state: GathererState) -> dict:
        """Gatherer produces structured result after searching."""
        user_prompt = build_gatherer_user_prompt(state)
        
        messages = [
            SystemMessage(content=GATHERER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ] + state["messages"] + [
            HumanMessage(content=GATHERER_DECISION_PROMPT)
        ]

        gatherer_structured_llm = llm.with_structured_output(GathererResult)
        result = await gatherer_structured_llm.ainvoke(messages)
        
        return {"gather_result": result}
    
    async def evaluator_node(state: GathererState) -> dict:
        """Evaluate if gathered data satisfies the Requirement request."""
        gatherer_result: GathererResult = state["gather_result"]
        
        user_prompt = build_evaluator_user_prompt(state, gatherer_result)
        messages = [
            SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
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


def create_requirement_handler_agent(model_id: str = "gpt-4o"):
    """Create the Requirement handler LangGraph agent."""
    
    llm = ChatOpenAI(model=model_id)
    gatherer_subgraph = create_gatherer_subgraph(llm)
    
    # Node 1: Parse Requirement items
    async def parse_requirement_node(state: RequirementAgentState) -> dict:
        """Parse raw Requirement requests into structured items."""
        require_items: List[RequireItem] = state["require_items"]
        
        user_prompt = build_parser_user_prompt(require_items)

        parser_llm = llm.with_structured_output(ParsedRequireItemList)
        parsed_require_items: ParsedRequireItemList = await parser_llm.ainvoke([
            SystemMessage(content=PARSER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
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
