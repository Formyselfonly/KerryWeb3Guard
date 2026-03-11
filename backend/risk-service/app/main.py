from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import get_settings
from app.schemas.common import HealthResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "KerryChainGuard backend service. "
        "Project Creator: Telegram @kerryzheng"
    ),
    contact={
        "name": "Kerry Zheng",
        "url": "https://t.me/kerryzheng",
    },
)

origins = [item.strip() for item in settings.cors_allow_origins.split(",") if item]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
