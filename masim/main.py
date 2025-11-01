from fastapi import FastAPI

from masim.api.router import animation, health, sessions
from masim.agents.utils import docker_prerequirements
from masim.config import create_checkpointer
from masim.services.animation import AnimationService

from contextlib import asynccontextmanager

from dotenv import load_dotenv

from rich.logging import RichHandler
from datetime import datetime
import logging
from pathlib import Path

load_dotenv()

# 로깅 설정
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

file_handler = logging.FileHandler(f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log", encoding="utf-8")
rich_handler = RichHandler()

handlers = [file_handler, rich_handler]

# 루트 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=handlers
)

# uvicorn 로거 가져오기 및 핸들러 교체
for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
    logger = logging.getLogger(name)
    logger.handlers = handlers
    logger.propagate = False

docker_prerequirements(build_image=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 초기화
    checkpointer = create_checkpointer()
    app.state.checkpointer = checkpointer
    app.state.animation_service = AnimationService(checkpointer)
    yield
    # 앱 종료 시 커넥션 닫기
    app.state.checkpointer.conn.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def root():
    return {}


app.include_router(animation.router)
app.include_router(health.router)
app.include_router(sessions.router)