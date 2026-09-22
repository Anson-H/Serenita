"""Program-owned processing progress, independent of model input and decisions."""
from contextlib import contextmanager
from copy import deepcopy
import json
from contextvars import ContextVar
from uuid import uuid4

from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS, MODEL_RETRY_DELAY_SECONDS
from backend.app.application.memory.step_timing import StepTiming


_observer = ContextVar('memory_progress_observer', default=None)
_step = ContextVar('memory_progress_step', default=None)
_frames = ContextVar('memory_progress_frames', default=())
_event = ContextVar('memory_progress_event', default=None)
_UNSET = object()


def current_step():
    step, event = _step.get(), _event.get()
    return step + ':' + event if step and event and ':' not in step else step


def model_retry_metadata(attempt, status):
    return {'attempt': attempt, 'max_attempts': MAX_MODEL_ATTEMPTS,
        'delay_seconds': MODEL_RETRY_DELAY_SECONDS if status == 'waiting' else 0, 'status': status}


def report_model_request(attempt, status, **errors):
    step = _step.get()
    if step is None:
        return
    retry = model_retry_metadata(attempt, status)
    frames = _frames.get()
    if frames:
        frames[-1]['details']['retry'] = retry
    report_progress(step, 'retrying' if status == 'waiting' else 'running',
        details={'retry': retry}, **errors)


def report_model_retry(error, attempt):
    from backend.app.core.model_retry import error_details as model_error_details
    attempt = getattr(error, 'memory_request_attempt', attempt)
    if attempt >= MAX_MODEL_ATTEMPTS:
        raise error
    diagnostic = model_error_details(error)
    report_model_request(attempt, 'waiting',
        error_code=diagnostic.get('code', diagnostic['type']), error_message=diagnostic['message'])


@contextmanager
def event_progress(event_id):
    """Keep each Event's latest steps separate within one processing attempt."""
    token = _event.set(event_id)
    try:
        yield
    finally:
        _event.reset(token)


def error_details(error):
    code = error.code if isinstance(error, SerenitaError) else type(error).__name__
    message = error.message if isinstance(error, SerenitaError) else f'处理因 {code} 失败。'
    details = (error.details or {}).get('validation_errors') if isinstance(error, SerenitaError) else None
    return {'error_code': code, 'error_message': message,
            **({'details': {'validation_errors': json.loads(json.dumps(details, ensure_ascii=False, allow_nan=False))}} if details else {})}


@contextmanager
def observe_progress(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def report_progress(step_id, status, *, parent_step_id=None, **details):
    for frame in reversed(_frames.get()):
        if frame['step_id'] == step_id:
            if status in {'completed', 'failed'} and 'retry' in frame['details']:
                frame['details']['retry'] = {**frame['details']['retry'], 'status': status, 'delay_seconds': 0}
            frame['status'] = status
            if parent_step_id is None:
                parent_step_id = frame['parent']
            details['details'] = {**deepcopy(frame['details']), **details.get('details', {})}
            if frame.get('has_children') or details['details'].get('operations'):
                details['details'].pop('input', None)
                details['details'].pop('output', None)
            details['details']['timing'] = frame['timing'].snapshot(status)
            frame['reported_details'] = deepcopy(frame['details'])
            frame['errors'] = {key: details[key] for key in ('error_code', 'error_message') if key in details}
            break
    callback = _observer.get()
    if callback:
        event_id = _event.get()
        if event_id:
            step_id = step_id if ':' in step_id else step_id + ':' + event_id
            if parent_step_id:
                parent_step_id = parent_step_id if ':' in parent_step_id else parent_step_id + ':' + event_id
        callback(deepcopy({'step_id': step_id, 'parent_step_id': parent_step_id or None,
                  'status': status, **details}))


@contextmanager
def processing_step(step_id, *, parent_step_id=None, retry=False, input=_UNSET):
    parent = parent_step_id if parent_step_id is not None else _step.get()
    for ancestor in _frames.get():
        ancestor['has_children'] = True
    details = {} if input is _UNSET else {'input': deepcopy(input)}
    token = _step.set(step_id)
    frame = {'step_id': step_id, 'parent': parent, 'status': 'running', 'details': details, 'timing': StepTiming()}
    frames_token = _frames.set((*_frames.get(), frame))
    try:
        report_progress(step_id, 'retrying' if retry else 'running', parent_step_id=parent, details=deepcopy(details))
        yield details
    except Exception as error:
        try:
            report_progress(step_id, 'failed', parent_step_id=parent, **error_details(error))
        except Exception:
            # Expired or revoked executions cannot append more progress. The
            # execution terminal/lease still exposes their interrupted step.
            pass
        raise
    else:
        if frame['status'] not in {'failed', 'skipped'}:
            report_progress(step_id, 'completed', parent_step_id=parent, **({'details': details} if details else {}))
        elif details != frame.get('reported_details'):
            report_progress(step_id, frame['status'], parent_step_id=parent, details=details, **frame.get('errors', {}))
    finally:
        _frames.reset(frames_token)
        _step.reset(token)


class MemoryProgressService:
    def __init__(self, memory, actor, member, task):
        self.memory, self.actor, self.member = memory, actor, member
        self.task = task

    def record(self, value):
        identity = str(uuid4())
        return self.memory.repository.write(self.actor, self.member, 'progress-' + identity,
            {'processing_steps': [{'attempt_id': self.task['attempt_id'], 'progress_id': identity,
                'details': {}, **value}]})


@contextmanager
def operation(name, input):
    """Capture only explicit business arguments and actual results in the active step."""
    record = {'name': name, 'input': deepcopy(input)}
    frames = _frames.get()
    if frames:
        frames[-1]['details'].setdefault('operations', []).append(record)
    try:
        yield record
    except Exception as error:
        record['error'] = error_details(error)
        raise


def call_operation(name, input, invoke):
    with operation(name, input) as record:
        result = invoke()
        record['output'] = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return result


def track_step(step_id):
    from functools import wraps
    from inspect import signature
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if _observer.get() is None:
                return function(*args, **kwargs)
            values = signature(function).bind(*args, **kwargs)
            values.apply_defaults()
            inputs = {key: value for key, value in values.arguments.items() if key not in {'self', 'actor', 'member'}}
            with processing_step(step_id, input=inputs) as details:
                result = function(*args, **kwargs)
                details['output'] = deepcopy(result)
                return result
        return wrapped
    return decorate
