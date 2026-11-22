import ast
import json
import logging
import inspect
import re
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.composition import create_agent
from core.orchestrator import Orchestrator
from core.audit_logger import get_events
from core.audit_logger import emit as emit_audit
from core.config import SUPPORTED_MODEL_PROVIDERS, load_config_from_env
from core.contracts.audit import make_event
from core.contracts.response import AgentResponse
from core.security.redaction import redact_sensitive_data
from core.contracts.execution import AgentContext
from core.contracts.workflow import WorkflowExecutionError
from apps.fraud.real import create_real_agent

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


class FraudInvestigationRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    user_id: Optional[str] = None


class FraudInvestigationResponse(BaseModel):
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    success: bool
    output: Optional[Any] = None
    investigation: Optional[dict[str, Any]] = None
    rag_references: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def get_agent():
    return create_agent()


@lru_cache(maxsize=1)
def get_orchestrator():
    return Orchestrator(agent=get_agent())


@lru_cache(maxsize=1)
def get_real_agent():
    return create_real_agent()


_session_customer_ids: dict[str, str] = {}


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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
        run_kwargs = {
            "session_id": payload.session_id,
            "user_id": payload.user_id,
        }
        if "request_id" in inspect.signature(agent.run).parameters:
            run_kwargs["request_id"] = request_id
        response = agent.run(payload.query, **run_kwargs)
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


def _extract_customer_id(query: str, supplied: Optional[str]) -> Optional[str]:
    if supplied:
        return supplied.strip().upper()
    matches = re.findall(r"\b([A-Z]\d+)\b", query, re.IGNORECASE)
    return matches[0].upper() if matches else None


def _parse_evidence_content(content: str) -> Any:
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        try:
            return ast.literal_eval(content)
        except (ValueError, SyntaxError):
            return None


def _build_investigation_payload(result, request_id: str, rag_references: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = result.as_dict()
    evidence_items = payload.pop("evidence", [])
    transactions: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    investigations: list[dict[str, Any]] = []
    graph_relationships: list[dict[str, Any]] = []
    graph_nodes: list[dict[str, Any]] = []

    for item in evidence_items:
        metadata = item.get("metadata") or {}
        step_id = metadata.get("step_id")
        parsed = _parse_evidence_content(item.get("content", ""))
        if not isinstance(parsed, dict):
            continue
        results = parsed.get("results") if isinstance(parsed.get("results"), list) else None
        if step_id == "transactions" and results:
            transactions.extend(results)
        elif step_id == "alerts" and results:
            alerts.extend(results)
        elif step_id == "investigations" and results:
            investigations.extend(results)
        elif step_id in {"resolve_subject", "customer_context", "fraud_context", "related_entities"}:
            if step_id == "resolve_subject":
                resolved_node = parsed.get("result")
                if isinstance(resolved_node, dict):
                    graph_nodes.append(resolved_node)
            elif results:
                for record in results:
                    relationship = record.get("relationship")
                    node = record.get("node")
                    if isinstance(relationship, dict):
                        graph_relationships.append({
                            "id": relationship.get("id"),
                            "source": relationship.get("source"),
                            "target": relationship.get("target"),
                            "type": relationship.get("type"),
                            "properties": relationship.get("properties") or {},
                            "direction": record.get("direction"),
                        })
                    if isinstance(node, dict):
                        graph_nodes.append(node)

    return {
        "summary": {
            "customer_id": payload["subject"]["customer_id"],
            "customer_name": payload["subject"].get("name"),
            "risk_assessment": payload["risk_assessment"],
            "findings": payload["findings"],
            "contributing_signals": payload["contributing_signals"],
            "resources_consulted": payload["resources_consulted"],
            "metadata": payload["metadata"],
        },
        "mysql": {
            "transactions": transactions,
            "fraud_alerts": alerts,
            "investigation_records": investigations,
        },
        "neo4j": {
            "nodes": graph_nodes,
            "relationships": graph_relationships,
        },
        "rag_references": rag_references or [],
        "evidence": evidence_items,
        "deterministic_assessment": True,
        "request_id": request_id,
    }


def _serialize_trace(request_id: str) -> list[dict[str, Any]]:
    events = []
    for event in get_events():
        if event.request_id != request_id:
            continue
        events.append(redact_sensitive_data(asdict(event)))
    return events


def _retrieve_rag_references(real_agent: Any, query: str) -> list[dict[str, Any]]:
    if not re.search(r"\b(risk|alert|device|guideline|investigation|evidence|policy|explain|reference|shared)\b", query, re.IGNORECASE):
        return []
    try:
        registry = getattr(real_agent, "planner", None)
        source_registry = getattr(registry, "knowledge_source_registry", None)
        rag_source = source_registry.get("rag")
        retrieved = rag_source.retrieve(query, k=3)
    except Exception:
        return []

    references = []
    for result in retrieved:
        if not isinstance(result, dict):
            continue
        references.append(redact_sensitive_data({
            "source": result.get("source") or result.get("document_name"),
            "document_name": result.get("document_name") or result.get("title") or result.get("document_title"),
            "section_title": result.get("section_title") or result.get("title"),
            "chunk_index": result.get("chunk_index"),
            "score": result.get("score"),
        }))
    return references


def _extract_rag_references(output: Any) -> list[dict[str, Any]]:
    if not isinstance(output, dict):
        return []
    references = []
    for result in output.get("results") or []:
        if not isinstance(result, dict):
            continue
        references.append(redact_sensitive_data({
            "source": result.get("source"),
            "document_name": result.get("document_name") or result.get("title") or result.get("document_title"),
            "section_title": result.get("section_title") or result.get("title"),
            "chunk_index": result.get("chunk_index"),
            "score": result.get("score"),
        }))
    return references


@app.post("/api/v1/fraud/investigate", response_model=FraudInvestigationResponse)
def investigate_fraud(payload: FraudInvestigationRequest):
    request_id = str(uuid.uuid4())
    session_id = payload.session_id or str(uuid.uuid4())
    actor = payload.user_id or "investigator"
    try:
        real_agent = get_real_agent()
    except Exception as exc:
        logger.exception("api.fraud.composition_error")
        emit_audit(make_event("request_completed", request_id=request_id, session_id=session_id, status="failed", metadata={"endpoint": "fraud_investigate", "failure_category": "configuration"}))
        return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=actor, success=False, error="Real fraud composition is unavailable. Configure the Neo4j and MySQL resources.", trace=_serialize_trace(request_id), metadata={"failure_category": "configuration", "authoritative": True, "retryable": False})
    customer_id = _extract_customer_id(payload.query, payload.customer_id)
    if customer_id is None and payload.session_id:
        customer_id = _session_customer_ids.get(payload.session_id)

    emit_audit(make_event("request_started", request_id=request_id, session_id=session_id, status="started", metadata={"endpoint": "fraud_investigate", "customer_id": customer_id}))

    if customer_id:
        _session_customer_ids[session_id] = customer_id
        workflow = real_agent.workflow_registry.get("fraud_investigation")
        context = AgentContext(request_id=request_id, session_id=session_id, user_id=actor)
        try:
            result = workflow.execute(
                {"workflow": "fraud_investigation", "query": payload.query, "query_kind": "investigation", "customer_id": customer_id},
                context,
            )
        except PermissionError as exc:
            return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=actor, success=False, error=str(exc), trace=_serialize_trace(request_id))
        except WorkflowExecutionError as exc:
            emit_audit(make_event("request_completed", request_id=request_id, session_id=session_id, status="failed", metadata={"endpoint": "fraud_investigate", "failure_category": exc.failure_category}))
            return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=actor, success=False, error=str(exc), trace=_serialize_trace(request_id), metadata={"failure_category": exc.failure_category, "authoritative": exc.authoritative, "retryable": exc.retryable})
        except Exception:
            logger.exception("api.fraud.unhandled_error", extra={"request_id": request_id, "session_id": session_id})
            return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=actor, success=False, error="Fraud investigation could not be completed because the required fraud data source is unavailable.", trace=_serialize_trace(request_id), metadata={"failure_category": "infrastructure", "authoritative": True, "retryable": False})

        rag_references = _retrieve_rag_references(real_agent, payload.query)
        investigation = _build_investigation_payload(result, request_id, rag_references)
        trace = _serialize_trace(request_id)
        emit_audit(make_event("request_completed", request_id=request_id, session_id=session_id, status="completed", metadata={"endpoint": "fraud_investigate", "customer_id": customer_id}))
        return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=actor, success=True, investigation=investigation, trace=trace, metadata={"workflow": "fraud_investigation", "selected_mode": "workflow"})

    if re.search(r"\b(investigate|investigation|suspicious|customer)\b", payload.query, re.IGNORECASE):
        return FraudInvestigationResponse(
            request_id=request_id,
            session_id=session_id,
            user_id=actor,
            success=False,
            error="A customer ID is required for this investigation request.",
            trace=_serialize_trace(request_id),
            metadata={"failure_category": "missing_customer", "authoritative": True, "retryable": True},
        )

    response = real_agent.run(payload.query, session_id=session_id, user_id=actor, request_id=request_id)
    rag_references = _extract_rag_references(response.output)
    trace = [_serialize_trace(request_id) if False else redact_sensitive_data(asdict(item) if hasattr(item, "__dataclass_fields__") else item) for item in (response.trace or [])]
    return FraudInvestigationResponse(request_id=request_id, session_id=session_id, user_id=response.metadata.get("user_id") or actor, success=response.success, output=redact_sensitive_data(response.output), rag_references=rag_references, trace=trace, error=redact_sensitive_data(response.error), metadata=redact_sensitive_data(response.metadata))


@app.get("/api/v1/status")
def system_status():
    config = load_config_from_env()
    components: dict[str, dict[str, str]] = {}

    components["fastapi"] = {"state": "available", "detail": "API process is responding"}
    components["model"] = {"state": "configured", "detail": config.model_provider}

    try:
        real_agent = get_real_agent()
    except Exception:
        real_agent = None

    if real_agent is None:
        components["mysql"] = {"state": "unavailable", "detail": "Real fraud configuration is not available"}
        components["neo4j"] = {"state": "unavailable", "detail": "Real fraud configuration is not available"}
        components["rag"] = {"state": "unknown", "detail": "RAG status could not be determined"}
        return {"status": "ok", "components": components}

    try:
        mysql_source = real_agent.execution_manager.knowledge_source_registry.get("business_db")
        mysql_source.schema_metadata()
        components["mysql"] = {"state": "available", "detail": "Read-only fraud source responded"}
    except Exception:
        components["mysql"] = {"state": "unavailable", "detail": "Could not reach MySQL"}

    try:
        graph = real_agent.knowledge_graph_registry.get("customer_graph")
        with graph._session() as session:
            session.run("RETURN 1 AS ok").consume()
        components["neo4j"] = {"state": "available", "detail": "Customer graph responded"}
    except Exception:
        components["neo4j"] = {"state": "unavailable", "detail": "Could not reach Neo4j"}

    try:
        rag_source = real_agent.planner.knowledge_source_registry.get("rag")
        documents = rag_source.pipeline.loader.load()
        components["rag"] = {"state": "available" if documents else "unavailable", "detail": f"{len(documents)} fraud reference document(s) configured"}
    except Exception:
        components["rag"] = {"state": "unknown", "detail": "RAG status could not be determined"}

    return {"status": "ok", "components": components}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        config = load_config_from_env()
        if config.model_provider not in SUPPORTED_MODEL_PROVIDERS:
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
