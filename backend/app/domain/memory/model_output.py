"""Parse complete JSON model output under the current output contract."""
import json
import re

def parse_json(content):
    block = re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*', content, flags=re.DOTALL)
    return json.loads(block.group(1) if block else content)

