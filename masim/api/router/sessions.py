from fastapi import APIRouter, HTTPException, status

from masim.api.deps import AnimationServiceDep

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("/{session_id}")
async def get_session_info(
    session_id: str,
    service: AnimationServiceDep
):
    """
    세션 정보 조회 (해당 세션의 모든 작업)
    
    - **session_id**: 세션 ID
    """
    jobs = service.list_jobs()
    session_jobs = [job for job in jobs if job.session_id == session_id]
    
    if not session_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    # 세션 상태 조회
    session_state = service.get_session_state(session_id)
    
    return {
        "session_id": session_id,
        "job_count": len(session_jobs),
        "jobs": session_jobs,
        "state": session_state
    }


@router.get("/{session_id}/jobs")
async def get_session_jobs(
    session_id: str,
    service: AnimationServiceDep
):
    """
    세션의 모든 작업 조회
    
    - **session_id**: 세션 ID
    """
    jobs = service.list_jobs()
    session_jobs = [job for job in jobs if job.session_id == session_id]
    
    return {
        "session_id": session_id,
        "jobs": session_jobs
    }


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    service: AnimationServiceDep
):
    """
    세션의 모든 작업 삭제
    
    - **session_id**: 세션 ID
    """
    jobs = service.list_jobs()
    session_jobs = [job for job in jobs if job.session_id == session_id]
    
    if not session_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    deleted_count = 0
    for job in session_jobs:
        if service.delete_job(job.job_id):
            deleted_count += 1
    
    return None