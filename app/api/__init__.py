from fastapi import APIRouter

from app.api.routes import router as _routes

router = APIRouter()
router.include_router(_routes)
