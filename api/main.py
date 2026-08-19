import logging
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from core.composition import create_agent
from core.contracts.response import AgentResponse

logger = logging.getLogger(__name__)


class AgentRunRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class AgentRunResponse(BaseModel):
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


def _serialize_response(response: AgentResponse) -> AgentRunResponse:
    metadata = response.metadata or {}
    trace = [
        asdict(item) if hasattr(item, "__dataclass_fields__") else item
        for item in (response.trace or [])
    ]

    return AgentRunResponse(
        request_id=metadata.get("request_id", "unknown"),
        session_id=metadata.get("session_id"),
        user_id=metadata.get("user_id"),
        success=response.success,
        output=response.output,
        error=response.error,
        trace=trace,
    )


app = FastAPI(
    title="Vexux-AI Agent API",
    version="1.0.0",
)


@app.post("/api/v1/agent/run", response_model=AgentRunResponse)
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

    return _serialize_response(response)
