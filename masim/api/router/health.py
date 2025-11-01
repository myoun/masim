from fastapi import APIRouter, status
from masim.agents.utils import current_datetime

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """기본 헬스체크"""
    return {
        "status": "healthy",
        "timestamp": current_datetime().isoformat(),
        "version": "1.0.0"
    }


@router.get("/", status_code=status.HTTP_200_OK)
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Masim API - Manim Animation Generation Service",
        "docs": "/docs",
        "health": "/health"
    }