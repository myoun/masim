from typing import Annotated
from fastapi import Depends, Request

from masim.services.animation import AnimationService

def get_animation_service(request: Request) -> AnimationService:
    return request.app.state.animation_service

AnimationServiceDep = Annotated[AnimationService, Depends(get_animation_service)]