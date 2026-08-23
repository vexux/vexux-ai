from dataclasses import dataclass, field
from typing import Any, Dict
from core.security.redaction import redact_sensitive_data


@dataclass
class Evidence:
    source: str
    content: str
    evidence_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceSet:
    items: list[Evidence] = field(default_factory=list)
    max_items: int = 10
    max_content_length: int = 4000

    def add(self, evidence: Evidence) -> None:
        if len(self.items) >= self.max_items:
            return
        evidence.content = redact_sensitive_data(evidence.content)[:self.max_content_length]
        self.items.append(evidence)

    def sources(self) -> list[str]:
        return list(dict.fromkeys(item.source for item in self.items))
