from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path

from masim.api.deps import AnimationServiceDep
from masim.models.request import CreateAnimationRequest
from masim.models.response import AnimationJob, JobStatus

router = APIRouter(prefix="/api/v1/animations", tags=["animations"])


@router.post("/jobs", response_model=AnimationJob, status_code=status.HTTP_201_CREATED)
async def create_animation_job(
    request: CreateAnimationRequest,
    background_tasks: BackgroundTasks,
    service: AnimationServiceDep,
):
    """
    새로운 애니메이션 작업 생성
    
    - **message**: 애니메이션 생성 요청 메시지
    - **session_id**: (선택) 이전 세션 ID를 제공하면 대화 이어가기
    - **user_id**: (선택) 사용자 ID
    """
    job = service.create_job(
        message=request.message,
        user_id=request.user_id,
        session_id=request.session_id
    )
    
    # 백그라운드에서 실행
    background_tasks.add_task(service.run_animation_async, job.job_id)
    
    return job


@router.get("/jobs/{job_id}", response_model=AnimationJob)
async def get_animation_job(
    job_id: str,
    service: AnimationServiceDep
):
    """
    작업 상태 조회
    
    - **job_id**: 작업 ID
    """
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    return job


@router.get("/jobs", response_model=list[AnimationJob])
async def list_animation_jobs(
    service: AnimationServiceDep,
    user_id: Optional[str] = None
):
    """
    작업 목록 조회
    
    - **user_id**: (선택) 특정 사용자의 작업만 필터링
    """
    jobs = service.list_jobs(user_id=user_id)
    return jobs


@router.get("/jobs/{job_id}/download")
async def download_animation(
    job_id: str,
    service: AnimationServiceDep
):
    """
    생성된 애니메이션 다운로드
    
    - **job_id**: 작업 ID
    """
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet (status: {job.status})"
        )
    
    if not job.result or not job.result.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found"
        )
    
    output_path = Path(job.result.output_path)
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file does not exist"
        )
    
    return FileResponse(
        path=str(output_path),
        media_type="video/mp4",
        filename=f"animation_{job_id}.mp4"
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_animation_job(
    job_id: str,
    service: AnimationServiceDep
):
    """
    작업 삭제
    
    - **job_id**: 작업 ID
    """
    success = service.delete_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    return None