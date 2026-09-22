"""Optional execution-owned accounting for every nested model call."""
from contextlib import contextmanager
from contextvars import ContextVar

_observer = ContextVar('model_call_observer', default=None)
_stream_observer = ContextVar('model_stream_observer', default=None)


@contextmanager
def model_call_scope(observer, *, stream_observer=None):
    token = _observer.set(observer)
    stream_token = _stream_observer.set(stream_observer)
    try:
        yield
    finally:
        _stream_observer.reset(stream_token)
        _observer.reset(token)


def current_model_stream_observer():
    return _stream_observer.get()


def observe_model_call(*, account_id, kind, model, payload, timeout_seconds, invoke):
    observer = _observer.get()
    if observer is None:
        return invoke(timeout_seconds)
    return observer(account_id=account_id, kind=kind, model=model, payload=payload,
                    timeout_seconds=timeout_seconds, invoke=invoke)
