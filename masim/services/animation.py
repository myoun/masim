from masim.agents.graph import create_animation_graph
from masim.models.response import AnimationJob, JobStatus, AnimationResult
from masim.models.state import State
from masim.agents.utils import current_datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from typing import Optional
from pathlib import Path

import uuid
import asyncio

import logging

logger = logging.getLogger()

class AnimationService:

    def __init__(self, checkpointer) -> None:
        self.graph = create_animation_graph(checkpointer)
        self.jobs: dict[str, AnimationJob] = {}

    def create_job(self, message: str, user_id: str | None = None, session_id: str | None = None) -> AnimationJob:
        job_id = str(uuid.uuid4())

        if session_id is None:
            session_id = str(uuid.uuid4())
            logger.info(f"Created new session: {session_id}")
        else:
            if not self._is_valid_session(session_id):
                logger.warning(f"Invalid session_id provided: {session_id}, creating new session")
                session_id = str(uuid.uuid4())
            else:
                logger.info(f"Reusing existing session: {session_id}")
        
        job = AnimationJob(
            job_id=job_id,
            session_id=session_id,
            status=JobStatus.PENDING,
            message=message,
            user_id=user_id,
            created_at=current_datetime()
        )

        self.jobs[job_id] = job
        logger.info(f"Created job {job_id} for user {user_id} with session {session_id}")
        
        return job
    def _is_valid_session(self, session_id: str) -> bool:
        """세션이 checkpointer에 존재하는지 확인"""
        try:
            config: RunnableConfig = {"configurable": {"thread_id": session_id}}
            state = self.graph.get_state(config)
            return state is not None and state.values is not None
        except Exception as e:
            logger.error(f"Failed to validate session {session_id}: {str(e)}")
            return False

    def get_job(self, job_id: str) -> AnimationJob | None:
        """작업 조회"""
        return self.jobs.get(job_id)
    
    def list_jobs(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> list[AnimationJob]:
        """작업 목록 조회"""
        jobs = list(self.jobs.values())
        
        if user_id:
            jobs = [job for job in jobs if job.user_id == user_id]
        
        if session_id:
            jobs = [job for job in jobs if job.session_id == session_id]
        
        # 최신순 정렬
        jobs.sort(key=lambda x: x.created_at, reverse=True)
        
        return jobs

    def delete_job(self, job_id: str) -> bool:
        """작업 삭제"""
        if job_id not in self.jobs:
            return False
        
        job = self.jobs[job_id]
        
        # 생성된 비디오 파일도 삭제
        if job.result and job.result.output_path:
            output_path = Path(job.result.output_path)
            if output_path.exists():
                try:
                    output_path.unlink()
                    logger.info(f"Deleted output file: {output_path}")
                except Exception as e:
                    logger.error(f"Failed to delete output file: {str(e)}")
        
        # 작업 정보 삭제
        del self.jobs[job_id]
        logger.info(f"Deleted job {job_id}")
        
        return True
    
    def get_session_info(self, session_id: str) -> Optional[dict]:
        """세션 정보 조회 (작업 목록 + 세션 상태)"""
        # 해당 세션의 작업들
        jobs = self.list_jobs(session_id=session_id)
        
        if not jobs:
            return None
        
        # LangGraph 세션 상태
        session_state = self.get_session_state(session_id)
        
        return {
            "session_id": session_id,
            "job_count": len(jobs),
            "jobs": [
                {
                    "job_id": job.job_id,
                    "message": job.message,
                    "status": job.status,
                    "created_at": job.created_at
                }
                for job in jobs
            ],
            "state": session_state
        }

    def get_session_state(self, session_id: str) -> Optional[dict]:
        """세션 상태 조회"""
        try:
            config: RunnableConfig = {"configurable": {"thread_id": session_id}}
            state = self.graph.get_state(config)
            return state.values if state else None
        except Exception as e:
            logger.error(f"Failed to get session state: {str(e)}")
            return None
    
    def run_animation(self, job_id: str) -> AnimationResult:
        """애니메이션 생성 실행"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        try:
            job.status = JobStatus.RUNNING
            job.started_at = current_datetime()
            
            config: RunnableConfig = {"configurable": {"thread_id": job.session_id}}
            
            # 기존 세션 확인
            existing_state = self.graph.get_state(config)
            
            if existing_state and existing_state.values:
                logger.info(f"Continuing session {job.session_id}")
                initial_state = State(
                    session_id=job.session_id,
                    messages=existing_state.values.get("messages", []) + [HumanMessage(job.message)],
                    max_retry=3,
                    retry=0,
                    codes=existing_state.values.get("codes", []),
                    plans=existing_state.values.get("plans", []),
                    analysis=existing_state.values.get("analysis", []),
                    goal=existing_state.values.get("goal", ""),
                    stdout="",
                    stderr="",
                    need_fix=False,
                    output_path=None
                )
            else:
                logger.info(f"Starting new session {job.session_id}")
                initial_state = State(
                    session_id=job.session_id,
                    messages=[HumanMessage(job.message)],
                    max_retry=3,
                    retry=0,
                    codes=[],
                    plans=[],
                    analysis=[],
                    goal="",
                    stdout="",
                    stderr="",
                    need_fix=False,
                    output_path=None
                )
            
            logger.info(f"Executing graph for job {job_id}")
            final_state = self.graph.invoke(initial_state, config=config)
            
            result = AnimationResult(
                output_path=final_state.get("output_path"),
                goal=final_state.get("goal", ""),
                plans=final_state.get("plans", []),
                codes=final_state.get("codes", []),
                stdout=final_state.get("stdout", ""),
                stderr=final_state.get("stderr", ""),
                retry_count=final_state.get("retry", 0)
            )
            
            job.status = JobStatus.COMPLETED
            job.completed_at = current_datetime()
            job.result = result
            
            logger.info(f"Job {job_id} completed")
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {str(e)}", exc_info=True)
            job.status = JobStatus.FAILED
            job.completed_at = current_datetime()
            job.error = str(e)
            raise
    
    async def run_animation_async(self, job_id: str) -> AnimationResult:
        """비동기 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run_animation, job_id)
