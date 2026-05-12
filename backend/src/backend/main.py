from fastapi import FastAPI
import gradio as gr

from backend.api.routes import router
from backend.core.config import settings
from backend.ui.gradio_app import build_ui


app = FastAPI(title=settings.app_name)
app.include_router(router)
app = gr.mount_gradio_app(app, build_ui(), path="/chat")
