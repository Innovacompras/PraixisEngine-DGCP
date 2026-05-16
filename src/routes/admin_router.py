from fastapi import APIRouter, Depends, Query
from src.dependencies.security import verify_admin_credentials
from src.controllers.admin_controller import (
    generate_api_key,
    get_all_usage,
    get_app_usage,
    get_health_status,
    get_system_stats,
    list_api_keys,
    revoke_api_key,
    delete_app_sessions,
    get_gpu,
    reset_gpu,
    get_global_audit,
    get_app_audit,
)

router = APIRouter(
    prefix="/api/system",
    tags=["System Admin"],
    dependencies=[Depends(verify_admin_credentials)]
)


@router.get("/health")
async def system_health_check():
    return await get_health_status()


@router.get("/stats")
async def system_statistics():
    return await get_system_stats()


@router.get("/keys")
async def list_keys():
    return await list_api_keys()


@router.post("/keys/generate")
async def create_app_key(app_name: str = Query(..., pattern=r"^[a-zA-Z0-9_-]{3,63}$")):
    return await generate_api_key(app_name)


@router.delete("/keys/revoke")
async def delete_app_key(api_key: str):
    return await revoke_api_key(api_key)


@router.delete("/sessions/{app_name}")
async def wipe_sessions(app_name: str):
    return await delete_app_sessions(app_name)


@router.get("/usage")
async def all_usage():
    return await get_all_usage()


@router.get("/usage/{app_name}")
async def app_usage(app_name: str):
    return await get_app_usage(app_name)


@router.get("/gpu")
async def gpu_status():
    return await get_gpu()


@router.post("/gpu/reset")
async def reset_gpu_slots():
    return await reset_gpu()


@router.get("/audit")
async def global_audit(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    return await get_global_audit(limit=limit, offset=offset)


@router.get("/audit/{app_name}")
async def app_audit(
    app_name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    return await get_app_audit(app_name=app_name, limit=limit, offset=offset)
