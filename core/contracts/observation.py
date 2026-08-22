from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Observation:

    success: bool

    output: Any = None

    error: Optional[str] = None

    summary: Optional[str] = None

    task_id: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)
