from pydantic import BaseModel, Field
from typing import Optional

class CreateAnimationRequest(BaseModel):
    """애니메이션 생성 요청"""
    message: str = Field(..., description="애니메이션 생성 요청 메시지", min_length=1)
    session_id: Optional[str] = Field(None, description="세션 ID (대화 이어가기)")
    user_id: Optional[str] = Field(None, description="사용자 ID")