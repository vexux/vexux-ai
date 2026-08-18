from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from core.contracts.observation import Observation

@dataclass
class Task:

    id: str

    description: str

    input: Dict[str, Any] = field(
        default_factory=dict
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class Plan:

    tasks: list[Task] = field(
        default_factory=list
    )


@dataclass
class AgentContext:

    request_id: str

    session_id: Optional[str] = None

    user_id: Optional[str] = None

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    current_plan: Optional[Plan] = None

    current_task: Optional[Task] = None

    observations: list[Observation] = field(
        default_factory=list
    )

    completed_tasks: list[Task] = field(
        default_factory=list
    )


@dataclass
class ExecutionResult:

    success: bool

    output: Any = None

    error: Optional[str] = None

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

@dataclass
class Intent:

    name: str

    confidence: float = 0.0

    entities: Dict[str, Any] = field(
        default_factory=dict
    )    