import re


_SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*|authorization\s*[=:]\s*)([^\s,;]+)"
)


def redact_sensitive_data(value):
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r"\1[REDACTED]", value)
    if isinstance(value, dict):
        return {key: redact_sensitive_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    return value
