from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Observation:

    success: bool

    output: Any = None

    error: Optional[str] = None

    summary: Optional[str] = None

    task_id: Optional[str] = None