from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AgentResponse:

    success: bool

    output: Any = None

    error: Optional[str] = None

    trace: Optional[list] = None