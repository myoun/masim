import docker
import docker.errors
import tempfile
import os
from pathlib import Path

docker_client = docker.from_env()
with open("generated.py", "r", encoding="utf8") as f:
    code = f.read()

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
        output = logs.decode("utf8")

        print({"output": output, "error": None})
    except docker.errors.ContainerError as e:
        print({"output": "", "stderr": e.stderr.decode("utf-8")}) # type: ignore
    except Exception as e:
        print({"output": "", "error": str(e)})