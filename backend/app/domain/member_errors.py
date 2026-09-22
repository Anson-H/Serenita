from backend.app.core.errors import SerenitaError


def member_error(code: str, message: str, kind: str = "forbidden") -> None:
    raise SerenitaError(kind, code, message)
