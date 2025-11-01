from pydantic import BaseModel
from masim.models.state import Plan, CodeAnalysis
from datetime import datetime
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class GoalExtractorResponse(BaseModel):
    goal: str

class PlanningAgentResponse(BaseModel):
    plans: list[Plan]

class CodingAgentResponse(BaseModel):
    code: str

class CodeAnalyzerResponse(BaseModel):
    need_fix: bool
    analysis: list[CodeAnalysis]

class AnimationResult(BaseModel):
    output_path: str | None = None
    goal: str
    plans: list[Plan]
    codes: list[str]
    stdout: str
    stderr: str
    retry_count: int

class AnimationJob(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    message: str
    user_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: AnimationResult | None = None
    error: str | None = None