"""Host evidence that a successful action request contained actual originals."""
import base64
from copy import deepcopy
import hashlib
import json


def retain_successful_model_resources(context, request):
    references = context.memory.setdefault('successful_model_resource_refs', [])
    known = {json.dumps(ref, sort_keys=True) for ref in references}
    for message in request.messages:
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get('type') not in {'image', 'file', 'audio', 'video'}:
                continue
            reference = part.get('model_resource_ref')
            if not isinstance(reference, dict) or not part.get('data_base64'):
                continue
            if reference.get('rendered_sha256'):
                try:
                    data = base64.b64decode(part['data_base64'], validate=True)
                except (ValueError, TypeError):
                    continue
                if hashlib.sha256(data).hexdigest() != reference['rendered_sha256']:
                    continue
            key = json.dumps(reference, sort_keys=True)
            if key not in known:
                references.append(deepcopy(reference))
                known.add(key)
