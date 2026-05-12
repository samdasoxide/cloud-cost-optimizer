import logging
import logging.config
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import init_db

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "structured",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
    }
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    logger.info("Cloud Cost Optimizer started")
    yield


app = FastAPI(
    title="Cloud Cost Optimizer",
    description="Identifies orphaned cloud resources and generates decommission commands.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"], summary="Liveness check")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


from app.api import router as api_router  # noqa: E402
from app.web import router as web_router  # noqa: E402

app.include_router(api_router, prefix="/api")
app.include_router(web_router)
