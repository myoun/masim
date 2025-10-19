from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from langchain_core.prompts import PromptTemplate
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage

from pydantic import BaseModel

from rich.logging import RichHandler
import logging

import operator
import dotenv
import docker
import docker.errors
import tempfile
import os

from pathlib import Path

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])
logger = logging.getLogger("Masim")

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
    output: str
    stderr: str
    analysis: list[CodeAnalysis]
    need_fix: bool

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

def coding_agnet(state: State):
    if "need_fix" in state and state["need_fix"]:
            template = PromptTemplate.from_file("./prompts/coding_agent_fix.md", encoding="utf8")
            value = template.invoke({"messages": state["messages"], "goal": state["goal"], "plans": state["plans"], "code": state["codes"][-1], "output": state["output"], "error": state["stderr"]})
    else:
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
                command=f"uv run manim {filename} Main",
                volumes={
                    str(Path(f.name).absolute()): {"bind": f"/sandbox/{filename}", "mode": "ro"},
                    str(output_dir.absolute()): {"bind": "/sandbox/media", "mode": "rw"}
                },
                working_dir="/sandbox",
                network_disabled=False,
                mem_limit="8g",
                stderr=True,
                stdout=True,
                remove=False,
                detach=False,
                user="runner",
                environment={"PYTHONUNBUFFERED": "1"},
            )
            output = logs.decode("utf-8")

            return {"output": output, "stderr": ""}
        except docker.errors.ContainerError as e:
            return {"output": "", "stderr": e.stderr.decode("utf-8")} # type: ignore
        except Exception as e:
            return {"output": "", "stderr": str(e)}

def code_analyzer(state: State):
    template = PromptTemplate.from_file("./prompts/code_analyzer.md", encoding="utf8")
    value = template.invoke({"code": state["codes"][-1], "output": state["output"], "stderr": state["stderr"]})

    llm = llms["mini"].with_structured_output(method="json_mode", schema=CodeAnalyzerResponse)
    response: CodeAnalyzerResponse = llm.invoke(value) # type: ignore

    need_fix = response.need_fix
    analysis = response.analysis
    
    return { "need_fix": need_fix, "analysis": analysis }

# ======== Conditional  ==========

def is_code_wrong(state: State):
    return "YES" if state["need_fix"] else "NO"

# ====================

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
graph.add_conditional_edges("code_analyzer", is_code_wrong, { "YES": "coding_agent", "NO": END })

app = graph.compile()

docker_prerequirements(build_image=False)

data = State(messages=[HumanMessage("경사하강법 설명해줘")]) # type: ignore

for event  in app.stream(
    data,
    stream_mode="debug"
):
    logger.info(event)