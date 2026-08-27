from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.common.auth.dependencies import require_auth
from backend.common.auth.models import AuthContext
from backend.common.contracts.models import UploadReservationRequest, UploadReservationResponse

from .service import UploadReservationService


def create_upload_router(service: UploadReservationService) -> APIRouter:
    router = APIRouter(tags=["uploads"])

    @router.post(
        "/uploads/reservations",
        response_model=UploadReservationResponse,
        response_model_exclude_none=False,
    )
    def reserve_upload(
        request: UploadReservationRequest,
        auth: AuthContext = Depends(require_auth),
    ) -> UploadReservationResponse:
        return service.reserve(auth.sub, request)

    return router
