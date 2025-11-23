from pathlib import Path
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

BASE_DIR = Path(__file__).resolve().parent.parent

PROMPTS_PATH = BASE_DIR / "prompts"
OUTPUT_PATH = BASE_DIR / "output"
LOGS_PATH = BASE_DIR / "logs"
DATA_PATH = BASE_DIR / "data"
SANDBOX_PATH = BASE_DIR / "sandbox"

SQLITE_PATH = DATA_PATH / "checkpoints.db"

def create_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)
    return SqliteSaver(conn)

LOGS_PATH.mkdir(exist_ok=True)
DATA_PATH.mkdir(exist_ok=True)