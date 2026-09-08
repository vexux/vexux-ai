import re


_SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*|authorization\s*[=:]\s*|"
    r"(?:password|passwd|secret|token)\s*[=:]\s*)([^\s,;]+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")
_SENSITIVE_KEYS = re.compile(
    r"(?i)^(?:api[_-]?key|authorization|password|passwd|secret|token|"
    r"access[_-]?token|refresh[_-]?token)$"
)


def redact_sensitive_data(value):
    if isinstance(value, str):
        redacted = _SECRET_PATTERN.sub(r"\1[REDACTED]", value)
        return _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\3", redacted)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEYS.match(str(key))
            else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    return value
