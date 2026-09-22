"""Host adapters for stateless SAG extraction and complete source inputs.

The host owns structured inputs, model budgets and stage execution. Copied
SAG parsers validate event shape and construct event/entity associations.
"""
import asyncio
import logging
from types import SimpleNamespace

# Upstream diagnostics include source text and query/entity labels. Detailed
# requests/results belong only in the host's permission-controlled audit log.
_logger = logging.getLogger('zleap.sag')
_logger.addHandler(logging.NullHandler())
_logger.propagate = False

from zleap.sag.modules.extract.processor import EventProcessor

from backend.app.core.time import local_timezone_name


def run_core(coroutine):
    # All application entry points are synchronous workers. Each adapter owns
    # its dependencies and authorized input values.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running = False
    else:
        running = True
    if not running:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RuntimeError('SAG must execute in the application worker, outside an event loop.')


class HostPromptManager:
    def __init__(self, config):
        self.config = config

    def get_template_config(self, name, **kwargs):
        if name != 'extract':
            raise ValueError('Unsupported SAG prompt')
        return self.config.values


class HostEventProcessor(EventProcessor):
    def __init__(self, prompt, *, llm_client=None, metadata=None):
        self.metadata = metadata or {}
        config = SimpleNamespace(timezone=local_timezone_name(), test_mode=False,
            custom_background=prompt.values.get('custom_background', ''),
            custom_requirements=prompt.extraction_requirements(),
            enable_strict_filtering=False)
        super().__init__(llm_client, HostPromptManager(prompt), config,
            entity_types=[])

    def _build_input(self, items, metadata, source_type):
        result = super()._build_input(items, metadata, source_type)
        result['data']['meta'].pop('entity_types', None)
        result['data']['meta'].pop('previous_context', None)
        result['data']['meta'].update(self.metadata)
        return result
