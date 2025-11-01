from masim.models.state import State
from masim.models.response import GoalExtractorResponse, PlanningAgentResponse, CodingAgentResponse, CodeAnalyzerResponse
from masim.agents.utils import get_llm, clean_docker_log, run_manim_in_docker
from masim.config import PROMPTS_PATH

from langchain_core.prompts import PromptTemplate

import tempfile
import os
import docker.errors

from pathlib import Path

import logging

logger = logging.getLogger()


def goal_extractor(state: State):
    template = PromptTemplate.from_file(PROMPTS_PATH/"goal_extractor.md", encoding="utf8")
    value = template.invoke({"message": state["messages"][0]})

    llm = get_llm("nano").with_structured_output(method="json_mode", schema=GoalExtractorResponse)
    response: GoalExtractorResponse = llm.invoke(value) # type: ignore
    goal = response.goal

    return { "goal" : goal }

def planing_agent(state: State):
    template = PromptTemplate.from_file(PROMPTS_PATH/"planning_agent.md", encoding="utf8")
    value = template.invoke({"messages": state["messages"], "goal": state["goal"]})

    llm = get_llm("nano").with_structured_output(method="json_mode", schema=PlanningAgentResponse)
    response: PlanningAgentResponse = llm.invoke(value) # type: ignore
    plans = response.plans

    return { "plans" : plans }

def coding_agnet(state: State):
    if "need_fix" in state and state["need_fix"]:
            template = PromptTemplate.from_file(PROMPTS_PATH/"coding_agent_fix.md", encoding="utf8")
            value = template.invoke({"messages": state["messages"], "goal": state["goal"], "plans": state["plans"], "code": state["codes"][-1], "stdout": state["stdout"], "stderr": state["stderr"]})
    else:
        template = PromptTemplate.from_file(PROMPTS_PATH/"coding_agent.md", encoding="utf8")
        value = template.invoke({"messages": state["messages"], "goal": state["goal"], "plans": state["plans"]})

    llm = get_llm("mini").with_structured_output(method="json_mode", schema=CodingAgentResponse)
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
            
            logs = run_manim_in_docker(f.name, filename, output_dir)

            stdout_full = logs.decode("utf-8")
            stdout = clean_docker_log(stdout_full)

            filename_without_extension = filename.split(".")[0]
            output_file = (output_dir/"videos"/filename_without_extension/"1080p60"/"output.mp4").absolute()
            if output_file.exists():
                logger.info(f"Manim video sucessfully saved at {output_file}!")
                return {"stdout": stdout, "stderr": "", "output_path": str(output_file)}
            else:
                return {"stdout": stdout, "stderr": "", "output_path": None}
        except docker.errors.ContainerError as e:
            return {"stdout": "", "stderr": e.stderr.decode("utf-8"), "output_path": None} # type: ignore
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "output_path": None}

def code_analyzer(state: State):
    template = PromptTemplate.from_file(PROMPTS_PATH/"code_analyzer.md", encoding="utf8")
    value = template.invoke({"code": state["codes"][-1], "stdout": state["stdout"], "stderr": state["stderr"]})

    llm = get_llm("nano").with_structured_output(method="json_mode", schema=CodeAnalyzerResponse)
    response: CodeAnalyzerResponse = llm.invoke(value) # type: ignore

    need_fix = response.need_fix
    analysis = response.analysis
    retry = state["retry"] + (1 if need_fix else 0)
    
    return { "need_fix": need_fix, "analysis": analysis, "retry": retry }