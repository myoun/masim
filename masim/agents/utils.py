from langchain.chat_models import init_chat_model
import docker
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from masim.config import SANDBOX_PATH

import logging

logger = logging.getLogger()

def get_llm(model):
    llms = {
        "nano": init_chat_model("openai:gpt-5-nano"),
        "mini": init_chat_model("openai:gpt-5-mini")
    }
    return llms[model]

docker_client = docker.from_env()

def docker_prerequirements(build_image: bool = False):
    if build_image:
        logger.info("Building Docker Image...")
        docker_client.images.build(path=str(SANDBOX_PATH), tag="sandbox:latest", encoding="utf8")
        logger.info("...Done!")

def clean_docker_log(log: str) -> str:
    return "\n".join(map(lambda line: line.strip(), filter(lambda line: not('\r' in line and ('%|' in line or 'it/s]' in line)), log.split("\n"))))

def run_manim_in_docker(
    python_file_path: str,
    filename: str,
    output_dir: Path,
    image: str = "sandbox:latest",
    memory_limit: str = "8g"
) -> bytes:
    """Docker 컨테이너에서 Manim 실행"""
    logs = docker_client.containers.run(
        image=image,
        command=f"uv run manim -o output.mp4 -qh {filename} Main",
        volumes={
            str(Path(python_file_path).absolute()): {"bind": f"/sandbox/{filename}", "mode": "ro"},
            str(output_dir.absolute()): {"bind": "/sandbox/media", "mode": "rw"}
        },
        working_dir="/sandbox",
        network_disabled=False,
        mem_limit=memory_limit,
        stderr=True,
        stdout=True,
        remove=True,
        detach=False,
        user="runner",
        environment={"PYTHONUNBUFFERED": "1"},
    )
    return logs

def current_datetime():
    return datetime.now(ZoneInfo("Asia/Seoul"))