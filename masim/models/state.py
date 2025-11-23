from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
import operator


class Plan(TypedDict):
    title: str
    description: str

class CodeAnalysis(TypedDict):
    issue: str
    fix: str

class State(TypedDict):
    messages: Annotated[list, add_messages]
    plans: list[Plan]
    goal: str
    codes: Annotated[list[str], operator.add]
    stdout: str
    stderr: str
    analysis: list[CodeAnalysis]
    need_fix: bool
    output_path: str | None
    max_retry: int
    retry: int
    session_id: str