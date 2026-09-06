from typing import Any, Literal

ErrorKind = Literal['invalid_input', 'unauthenticated', 'forbidden', 'missing', 'conflict', 'resource_limit', 'unsupported', 'invalid_structure', 'upstream_failure', 'timeout']


class SerenitaError(Exception):
    """A domain failure; transports choose how to present its category."""

    def __init__(self, kind: ErrorKind, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.kind = kind
        self.code = code
        self.message = message
        self.details = details

    @property
    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **({"details": self.details} if self.details is not None else {})}


def raise_error(kind: ErrorKind, code: str, message: str):
    raise SerenitaError(kind, code, message)
