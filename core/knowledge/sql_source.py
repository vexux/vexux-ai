import re


class SQLKnowledgeSource:
    name = "sql"
    description = "Read-only structured queries over an injected data backend."
    capabilities = ["structured_query", "metadata_lookup"]

    def __init__(self, backend):
        self.backend = backend

    def retrieve(self, query, k=None):
        normalized = query.strip()
        if not re.match(r"(?is)^select\b", normalized) or ";" in normalized.rstrip(";"):
            raise ValueError("SQL knowledge source accepts one read-only SELECT statement.")
        rows = self.backend.execute(normalized)
        return list(rows) if k is None else list(rows)[:k]

    def schema_metadata(self):
        return self.backend.schema_metadata() if hasattr(self.backend, "schema_metadata") else {}
