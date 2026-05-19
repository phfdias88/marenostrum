from fastapi import APIRouter

from app.controllers.auth import router as auth_router
from app.controllers.contact import router as contact_router
from app.controllers.demand import router as demand_router
from app.controllers.voting_place import router as voting_place_router
from app.controllers.webhook import router as webhook_router

# Agregador (montado em /api/v1 no main.py)
api_router = APIRouter(prefix="/v1")
api_router.include_router(auth_router)
api_router.include_router(contact_router)
api_router.include_router(demand_router)
api_router.include_router(voting_place_router)
api_router.include_router(webhook_router)
