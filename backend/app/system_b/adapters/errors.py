"""Sanitized upstream failures; no response bodies or credential-bearing URLs."""


class SystemAError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SystemAUnavailableError(SystemAError):
    """Timeout, network failure, or upstream 5xx."""


class SystemANotFoundError(SystemAError):
    """HTTP 404; distinct from a successful empty result."""


class SystemAHTTPError(SystemAError):
    """Unexpected HTTP status, including 3xx, 4xx other than 404, and 204."""


class SystemAResponseValidationError(SystemAError):
    """Malformed response or inconsistent dataset/page metadata."""
