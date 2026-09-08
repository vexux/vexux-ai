import logging
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from core.composition import create_agent
from core.orchestrator import Orchestrator
from core.audit_logger import get_events
from core.audit_logger import emit as emit_audit
from core.config import load_config_from_env
from core.contracts.audit import make_event
from core.contracts.response import AgentResponse
from core.security.redaction import redact_sensitive_data

logger = logging.getLogger(__name__)


class AgentRunRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    agent: Optional[str] = None
    workflow: Optional[str] = None
    delegations: Optional[list[dict[str, Any]]] = None


class AgentRunResponse(BaseModel):
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    orchestration_id: Optional[str] = None
    success: bool
    output: Any = None
    error: Optional[str] = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyAgentRunResponse(BaseModel):
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    success: bool
    output: Any = None
    error: Optional[str] = None
    trace: list[dict[str, Any]] = Field(default_factory=list)


@lru_cache(maxsize=1)
def get_agent():
    return create_agent()


@lru_cache(maxsize=1)
def get_orchestrator():
    return Orchestrator(agent=get_agent())


def _serialize_response(response: AgentResponse) -> AgentRunResponse:
    metadata = response.metadata or {}
    trace = [
        redact_sensitive_data(asdict(item) if hasattr(item, "__dataclass_fields__") else item)
        for item in (response.trace or [])
    ]

    return AgentRunResponse(
        request_id=metadata.get("request_id", "unknown"),
        session_id=metadata.get("session_id"),
        user_id=metadata.get("user_id"),
        orchestration_id=metadata.get("orchestration_id"),
        success=response.success,
        output=redact_sensitive_data(response.output),
        error=redact_sensitive_data(response.error),
        trace=trace,
        metadata=redact_sensitive_data(metadata),
    )


app = FastAPI(
    title="Vexux-AI Agent API",
    version="1.0.0",
)


@app.post("/api/v1/agent/run", response_model=LegacyAgentRunResponse)
def run_agent(
    payload: AgentRunRequest,
    request: Request,
    agent=Depends(get_agent),
):
    logger.info(
        "api.agent.request",
        extra={
            "session_id": payload.session_id,
            "user_id": payload.user_id,
            "path": request.url.path,
        },
    )

    request_id = str(uuid.uuid4())
    emit_audit(make_event("request_started", request_id=request_id, session_id=payload.session_id, status="started", metadata={"endpoint": "agent"}))
    try:
        response = agent.run(
            payload.query,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
    except Exception as exc:
        logger.exception(
            "api.agent.unhandled_error",
            extra={
                "session_id": payload.session_id,
                "user_id": payload.user_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Agent execution failed.",
        ) from exc

    serialized = _serialize_response(response)
    if serialized.request_id == "unknown":
        serialized.request_id = request_id
    emit_audit(make_event("request_completed", request_id=serialized.request_id, session_id=payload.session_id, status="completed" if serialized.success else "failed", metadata={"endpoint": "agent"}))
    return serialized


@app.post("/api/v1/orchestrator/run", response_model=AgentRunResponse)
def run_orchestrator(
    payload: AgentRunRequest,
    request: Request,
    orchestrator=Depends(get_orchestrator),
):
    request_id = str(uuid.uuid4())
    logger.info(
        "api.orchestrator.request",
        extra={"request_id": request_id, "path": request.url.path},
    )
    orchestration_request = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)
    emit_audit(make_event("request_started", request_id=request_id, session_id=payload.session_id, status="started", metadata={"endpoint": "orchestrator"}))
    try:
        response = orchestrator.run(
            orchestration_request,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
    except Exception as exc:
        logger.exception("api.orchestrator.unhandled_error")
        raise HTTPException(status_code=500, detail="Orchestrator execution failed.") from exc

    serialized = _serialize_response(response)
    if serialized.request_id == "unknown":
        serialized.request_id = request_id
    emit_audit(make_event("request_completed", request_id=request_id, session_id=payload.session_id, orchestration_id=serialized.orchestration_id, status="completed" if serialized.success else "failed", metadata={"endpoint": "orchestrator"}))
    return serialized


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        config = load_config_from_env()
        supported = {"mistral", "qwen", "ollama", "fake"}
        if config.model_provider not in supported:
            raise ValueError(f"Unsupported MODEL_PROVIDER: {config.model_provider}")
        return {"status": "ready", "model_provider": config.model_provider}
    except ValueError as exc:
        raise HTTPException(status_code=503, detail={"error": "configuration_error", "message": str(exc)}) from exc


@app.get("/api/v1/orchestrator/{request_id}/trace")
def get_orchestration_trace(request_id: str):
    events = []
    for event in get_events():
        payload = redact_sensitive_data(asdict(event))
        if event.request_id == request_id or event.orchestration_id == request_id:
            events.append(payload)
    return {"request_id": request_id, "events": events}
