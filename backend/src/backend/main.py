from fastapi import FastAPI

from backend.api.routes import router
from backend.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(router)
