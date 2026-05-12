import logging
import logging.config

from fastapi import FastAPI

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

app = FastAPI(
    title="Cloud Cost Optimizer",
    description="Identifies orphaned cloud resources and generates decommission commands.",
    version="0.1.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    logger.info("Cloud Cost Optimizer started")


from app.api import router as api_router  # noqa: E402
from app.web import router as web_router  # noqa: E402

app.include_router(api_router, prefix="/api")
app.include_router(web_router)
