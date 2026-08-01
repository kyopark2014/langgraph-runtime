from fastapi import APIRouter

from application.services.config_service import get_application_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config():
    return get_application_config()
