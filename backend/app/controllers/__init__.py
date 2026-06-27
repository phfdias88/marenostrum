from fastapi import APIRouter, Depends

from app.controllers.audit import router as audit_router
from app.controllers.auth import router as auth_router
from app.controllers.census import router as census_router
from app.controllers.contact import router as contact_router
from app.controllers.agenda_event import router as agenda_router
from app.controllers.demand import router as demand_router
from app.controllers.message_template import router as template_router
from app.controllers.monitored import router as monitored_router
from app.controllers.tse import router as tse_router
from app.controllers.voting_place import router as voting_place_router
from app.controllers.webhook import router as webhook_router
from app.core.dependencies import require_area

# Agregador (montado em /api/v1 no main.py)
api_router = APIRouter(prefix="/v1")
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(contact_router)
# Demandas e Agenda são dados privados do gabinete — o acesso é configurável
# pelo owner por usuário (require_area dá 403 se desligado pra quem não é owner).
api_router.include_router(demand_router, dependencies=[Depends(require_area("demands_enabled"))])
api_router.include_router(voting_place_router)
api_router.include_router(tse_router)
api_router.include_router(monitored_router)
api_router.include_router(template_router)
api_router.include_router(agenda_router, dependencies=[Depends(require_area("agenda_enabled"))])
api_router.include_router(census_router)
api_router.include_router(webhook_router)
