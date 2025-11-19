from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage

from pydantic import BaseModel

from rich.logging import RichHandler
from rich.prompt import Prompt
from datetime import datetime
import logging

import operator
import dotenv
import docker
import docker.errors
import tempfile
import os
import uuid
from enum import Enum

from pathlib import Path

dotenv.load_dotenv()

log_dir = Path("logs")
if not log_dir.exists():
    log_dir.mkdir()

file_handler = logging.FileHandler(f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log", encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", handlers=[RichHandler(), file_handler])
logger = logging.getLogger("Masim")

class Interruption(Enum):
    PLAN_REVIEW = "plan_review"
    HUMAN_REVIEW_CONFIRM = "human_review_confirm"
    HUMAN_REVIEW_COMMENT = "human_review_comment"

class AgentState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    PLAN_REVIEW = "PLAN_REVIEW"
    HUMAN_REVIEW_CONFIRM = "HUMAN_REVIEW_CONFIRM"
    HUMAN_REVIEW_COMMENT = "HUMAN_REVIEW_COMMENT"

# ===============

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
    human_request: str
    plan_feedback: str

llms = {
    "nano": init_chat_model("openai:gpt-5-nano"),
    "mini": init_chat_model("openai:gpt-5-mini")
}

docker_client = docker.from_env()

def docker_prerequirements(build_image: bool = False):
    if build_image:
        logger.info("Building Docker Image...")
        docker_client.images.build(path="./sandbox", tag="sandbox:latest", encoding="utf8")
        logger.info("...Done!")

def clean_docker_log(log: str) -> str:
    return "\n".join(map(lambda line: line.strip(), filter(lambda line: not('\r' in line and ('%|' in line or 'it/s]' in line)), log.split("\n"))))

# ======================

class GoalExtractorResponse(BaseModel):
    goal: str

class PlanningAgentResponse(BaseModel):
    plans: list[Plan]

class CodingAgentResponse(BaseModel):
    code: str

class CodeAnalyzerResponse(BaseModel):
    need_fix: bool
    analysis: list[CodeAnalysis]

# =====================
def goal_extractor(state: State):
    template = PromptTemplate.from_file("./prompts/goal_extractor.md", encoding="utf8")
    value = template.invoke({"message": state["messages"][0]})

    llm = llms["nano"].with_structured_output(method="json_mode", schema=GoalExtractorResponse)
    response: GoalExtractorResponse = llm.invoke(value) # type: ignore
    goal = response.goal

    return { "goal" : goal }

def planing_agent(state: State):
    template = PromptTemplate.from_file("./prompts/planning_agent.md", encoding="utf8")
    value = template.invoke({"messages": state["messages"], "goal": state["goal"]})

    llm = llms["nano"].with_structured_output(method="json_mode", schema=PlanningAgentResponse)
    response: PlanningAgentResponse = llm.invoke(value) # type: ignore
    plans = response.plans

    return { "plans" : plans }

def plan_review(state: State):
    feedback = interrupt(Interruption.PLAN_REVIEW)
    return { "plan_feedback": feedback }

def plan_reviser(state: State):
    template = PromptTemplate.from_file("./prompts/plan_reviser.md", encoding="utf8")
    value = template.invoke({"goal": state["goal"], "plans": state["plans"], "feedback": state["plan_feedback"]})

    llm = llms["nano"].with_structured_output(method="json_mode", schema=PlanningAgentResponse)
    response: PlanningAgentResponse = llm.invoke(value) # type: ignore
    plans = response.plans

    return { "plans": plans }

def coding_agnet(state: State):
    template = PromptTemplate.from_file("./prompts/coding_agent.md", encoding="utf8")
    value = template.invoke({"messages": state["messages"], "goal": state["goal"], "plans": state["plans"]})

    llm = llms["mini"].with_structured_output(method="json_mode", schema=CodingAgentResponse)
    response: CodingAgentResponse = llm.invoke(value) # type: ignore
    code = response.code

    return { "codes" : [code] }

def code_runner(state: State):
    code = state["codes"][-1]
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=True, encoding="utf8") as f:
        f.write(code)
        f.flush()
        filename = os.path.basename(f.name)

        try:
            output_dir = Path.cwd() / "output"
            output_dir.mkdir(exist_ok=True)
            
            logs = docker_client.containers.run(
                image="sandbox:latest",
                command=f"uv run manim -o output.mp4 -qh {filename} Main",
                volumes={
                    str(Path(f.name).absolute()): {"bind": f"/sandbox/{filename}", "mode": "ro"},
                    str(output_dir.absolute()): {"bind": "/sandbox/media", "mode": "rw"}
                },
                working_dir="/sandbox",
                network_disabled=False,
                mem_limit="8g",
                stderr=True,
                stdout=True,
                remove=True,
                detach=False,
                user="runner",
                environment={"PYTHONUNBUFFERED": "1"},
            )
            stdout_full = logs.decode("utf-8")
            stdout = clean_docker_log(stdout_full)

            filename_without_extension = filename.split(".")[0]
            output_file = (output_dir/"videos"/filename_without_extension/"1080p60"/"output.mp4").absolute()
            if output_file.exists():
                return {"stdout": stdout, "stderr": "", "output_path": str(output_file)}
            else:
                return {"stdout": stdout, "stderr": "", "output_path": None}
        except docker.errors.ContainerError as e:
            return {"stdout": "", "stderr": e.stderr.decode("utf-8"), "output_path": None} # type: ignore
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "output_path": None}

def code_analyzer(state: State):
    template = PromptTemplate.from_file("./prompts/code_analyzer.md", encoding="utf8")
    value = template.invoke({"code": state["codes"][-1], "stdout": state["stdout"], "stderr": state["stderr"]})

    llm = llms["nano"].with_structured_output(method="json_mode", schema=CodeAnalyzerResponse)
    response: CodeAnalyzerResponse = llm.invoke(value) # type: ignore

    need_fix = response.need_fix
    analysis = response.analysis
    retry = state["retry"] + (1 if need_fix else 0)
    
    return { "need_fix": need_fix, "analysis": analysis, "retry": retry }

def human_review(state: State):
    while True:
        need_fix = interrupt(Interruption.HUMAN_REVIEW_CONFIRM)

        if need_fix not in ["Y", "N"]:
            continue
        elif need_fix == "N":
            return { "need_fix": False }
        else:
            request = interrupt(Interruption.HUMAN_REVIEW_COMMENT)
            return { "human_request": request, "need_fix": True }
        
def fix_planner(state: State):
    template = PromptTemplate.from_file("./prompts/fix_planner.md", encoding="utf8")
    value = template.invoke({"code": state["codes"][-1], "human_request": state.get("human_request", "없음"), "analysis": state["analysis"]})

    llm = llms["nano"].with_structured_output(method="json_mode", schema=PlanningAgentResponse)
    response: PlanningAgentResponse = llm.invoke(value) # type: ignore
    plans = response.plans

    return { "plans": plans }

def fix_coding_agent(state: State):
    template = PromptTemplate.from_file("./prompts/coding_agent_fix.md", encoding="utf8")
    value = template.invoke({"plans": state["plans"], "code": state["codes"][-1]})

    llm = llms["mini"].with_structured_output(method="json_mode", schema=CodingAgentResponse)
    response: CodingAgentResponse = llm.invoke(value) # type: ignore
    code = response.code

    return { "codes" : [code] }

# ======== Conditional  ==========

def code_analyzer_router(state: State):
    return "FIX" if state["need_fix"] and state["retry"] <= state["max_retry"] else "GOOD"

def plan_feedback_router(state: State):
    return "REVISE" if state.get("plan_feedback") else "APPROVE"

# ====================

graph = StateGraph(State)

graph.add_node("goal_extractor", goal_extractor)
graph.add_node("planning_agent", planing_agent)
graph.add_node("plan_review", plan_review)
graph.add_node("plan_reviser", plan_reviser)
graph.add_node("coding_agent", coding_agnet)
graph.add_node("code_runner", code_runner)
graph.add_node("code_analyzer", code_analyzer)
graph.add_node("human_review", human_review)
graph.add_node("fix_planner", fix_planner)
graph.add_node("fix_coding_agent", fix_coding_agent)

graph.add_edge(START, "goal_extractor")
graph.add_edge("goal_extractor", "planning_agent")
graph.add_edge("planning_agent", "plan_review")
graph.add_conditional_edges("plan_review", plan_feedback_router, { "REVISE": "plan_reviser", "APPROVE": "coding_agent" })
graph.add_edge("plan_reviser", "plan_review")
graph.add_edge("coding_agent", "code_runner")
graph.add_edge("code_runner", "code_analyzer")
graph.add_conditional_edges("code_analyzer", code_analyzer_router, { "FIX": "fix_planner", "GOOD": "human_review" })
graph.add_conditional_edges("human_review", code_analyzer_router, { "FIX": "fix_planner", "GOOD": END })
graph.add_edge("fix_planner", "fix_coding_agent")
graph.add_edge("fix_coding_agent", "code_runner")

checkpointer = InMemorySaver()
thread_id = str(uuid.uuid4())
config: RunnableConfig = {"run_name": "Masim Agent", "configurable": {"thread_id": thread_id}}

app = graph.compile(checkpointer=checkpointer).with_config(config=config)

if __name__ == "__main__":
    with open("graph.png", "wb") as f:
        f.write(app.get_graph().draw_mermaid_png())

    docker_prerequirements(build_image=False)

    data = State(session_id=thread_id,messages=[HumanMessage("원의 넓이 공식을 평행사변형을 이용해서 유도하는 애니메이션 제작")], max_retry=5, retry=0) # type: ignore

    result = app.invoke(data)

    while True:
        q: list = result["__interrupt__"]

        if len(q) == 0:
            break
        
        i = q.pop(0)
        res = Prompt.ask(i.value)

        result = app.invoke(Command(resume=res))