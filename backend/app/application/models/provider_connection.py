"""Provider credential checks shared by account and administrator settings."""
from backend.app.application.models.provider_errors import raise_provider_error
from backend.app.core.errors import SerenitaError
from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError


def test_provider_connection(provider, *, api_url, api_key, cancellation_token=None):
    try:
        result = provider.test_connection(api_url=api_url, api_key=api_key,
            cancellation_token=cancellation_token)
    except (ProviderChatCompletionError, ProviderModelListError) as error:
        raise_provider_error(error)
    if not result.reachable:
        code = result.code or "MODEL_ERROR"
        raise SerenitaError("timeout" if code == "MODEL_TIMEOUT" else "upstream_failure",
            code, result.message, details=result.details)
    return {"provider_id": result.provider_id, "reachable": True, "message": result.message}
