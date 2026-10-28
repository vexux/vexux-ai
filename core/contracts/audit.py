from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


@dataclass
class AuditEvent:
    event_id: str
    timestamp: str
    request_id: Optional[str]
    session_id: Optional[str]
    orchestration_id: Optional[str]
    task_id: Optional[str]
    agent_name: Optional[str]
    event_type: str
    status: Optional[str]
    resource_type: Optional[str]
    resource_name: Optional[str]
    action: Optional[str]
    duration_ms: Optional[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


def make_event(
    event_type: str,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    orchestration_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    action: Optional[str] = None,
    duration_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
        session_id=session_id,
        orchestration_id=orchestration_id,
        task_id=task_id,
        agent_name=agent_name,
        event_type=event_type,
        status=status,
        resource_type=resource_type,
        resource_name=resource_name,
        action=action,
        duration_ms=duration_ms,
        metadata=metadata or {},
    )
