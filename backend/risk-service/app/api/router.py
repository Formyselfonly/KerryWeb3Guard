from fastapi import APIRouter

from app.api.routes.blacklist import router as blacklist_router
from app.api.routes.learn import router as learn_router
from app.api.routes.meta import router as meta_router
from app.api.routes.scan import router as scan_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(scan_router)
api_router.include_router(learn_router)
api_router.include_router(blacklist_router)
api_router.include_router(meta_router)
