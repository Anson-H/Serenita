from backend.app.core.errors import SerenitaError

HTTP_STATUS_BY_ERROR_KIND = {
    'invalid_input': 400, 'unauthenticated': 401, 'forbidden': 403,
    'missing': 404, 'conflict': 409, 'resource_limit': 413,
    'unsupported': 415, 'invalid_structure': 422, 'upstream_failure': 502, 'timeout': 504,
}


def error_http_status(error: SerenitaError) -> int:
    return HTTP_STATUS_BY_ERROR_KIND[error.kind]
