import asyncio
import mimetypes
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Admin UI"])

_ROUTES_DIR     = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR  = os.path.normpath(os.path.join(_ROUTES_DIR, "..", "admin_panel"))
_STATIC_DIR     = os.path.normpath(os.path.join(_ROUTES_DIR, "..", "admin_panel", "static"))

templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_ui(request: Request):
    return templates.TemplateResponse(request, "base.html")


@router.get("/static/{filepath:path}", include_in_schema=False)
async def serve_static(filepath: str):
    """Serves files from the static/ directory as a regular route."""
    abs_path = os.path.normpath(os.path.join(_STATIC_DIR, filepath))

    if not abs_path.startswith(_STATIC_DIR + os.sep) and abs_path != _STATIC_DIR:
        raise HTTPException(status_code=404)

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404)

    content = await asyncio.to_thread(_read_file, abs_path)

    media_type, _ = mimetypes.guess_type(abs_path)
    return Response(content=content, media_type=media_type or "application/octet-stream")


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
