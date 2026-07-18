"""FastAPI application for the recruitment agent platform.

Single Lambda entrypoint behind API Gateway (via Mangum). Each agent contributes
an APIRouter that is mounted here — add new agents by importing their router and
calling app.include_router(...).
"""
from fastapi import FastAPI
from mangum import Mangum

from recruitment.dcp.routes import router as dcp_router

app = FastAPI(title="Recruitment Agent Platform")

app.include_router(dcp_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# API Gateway (proxy integration) entrypoint
handler = Mangum(app)
