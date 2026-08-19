from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentResponse:

    success: bool

    output: Any = None

    error: Optional[str] = None

    trace: Optional[list] = None

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )