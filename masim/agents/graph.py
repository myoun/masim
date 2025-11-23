from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from masim.models.state import State
from masim.agents.nodes import goal_extractor, planing_agent, coding_agnet, code_runner, code_analyzer
from masim.agents.conditional import code_analyzer_router

def create_animation_graph(checkpointer) -> CompiledStateGraph:
    graph = StateGraph(State)

    graph.add_node("goal_extractor", goal_extractor)
    graph.add_node("planning_agent", planing_agent)
    graph.add_node("coding_agent", coding_agnet)
    graph.add_node("code_runner", code_runner)
    graph.add_node("code_analyzer", code_analyzer)

    graph.add_edge(START, "goal_extractor")
    graph.add_edge("goal_extractor", "planning_agent")
    graph.add_edge("planning_agent", "coding_agent")
    graph.add_edge("coding_agent", "code_runner")
    graph.add_edge("code_runner", "code_analyzer")
    graph.add_conditional_edges("code_analyzer", code_analyzer_router, { "FIX": "coding_agent", "END": END })

    return graph.compile(checkpointer=checkpointer)
