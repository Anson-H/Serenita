"""Local tokenizers for context estimates; no network requests or extra allowance."""
from dataclasses import dataclass
from functools import lru_cache
import base64
import hashlib
import json
from pathlib import Path
import re

import tiktoken
from tiktoken.model import encoding_name_for_model
from tokenizers import Tokenizer

from zleap.sag.modules.load.chunking.tokenizer.estimator import DEFAULT_TOKENIZER_JSON_PATH


ASSET_ROOT = Path(__file__).with_name("tokenizer_assets")


@lru_cache(maxsize=1)
def tokenizer_manifest():
    return json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=6)
def _load(name):
    suffix = ".tiktoken" if name in {"cl100k_base", "o200k_base"} else ".json"
    entry = tokenizer_manifest()[name + suffix]
    path = DEFAULT_TOKENIZER_JSON_PATH if name == "qwen" else ASSET_ROOT / (name + suffix)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"分词器文件校验失败：{name}")
    if suffix == ".tiktoken":
        ranks = {base64.b64decode(token): int(rank)
                 for token, rank in (line.split() for line in data.splitlines() if line)}
        return tiktoken.Encoding(**entry["encoding"], mergeable_ranks=ranks)
    tokenizer = Tokenizer.from_str(data.decode("utf-8"))
    # Counting must never inherit a tokenizer's padding or truncation policy.
    tokenizer.no_padding()
    tokenizer.no_truncation()
    return tokenizer


@dataclass(frozen=True)
class TextTokenCounter:
    name: str
    match: str

    def count(self, text: str) -> int:
        if not text:
            return 0
        tokenizer = _load(self.name)
        if isinstance(tokenizer, tiktoken.Encoding):
            return len(tokenizer.encode_ordinary(text))
        return len(tokenizer.encode(text, add_special_tokens=False).ids)


def text_token_counter(model=None):
    """Resolve remote identities, including OpenRouter names, without claiming API accuracy."""
    model = model or {}
    remote = str(model.get("remote_model_id") or model.get("model_id") or "").lower()
    remote = remote.rsplit("/", 1)[-1]
    remote = re.sub(r"^(?:aliyun_bailian|deepseek|openrouter|openai):", "", remote)
    remote = remote.split(":", 1)[0]
    if remote.startswith("qwen"):
        newer = re.match(r"qwen(\d+)(?:\.(\d+))?", remote)
        version = tuple(int(value or 0) for value in newer.groups()) if newer else (0, 0)
        return TextTokenCounter("qwen35" if version >= (3, 5) else "qwen", "family")
    if remote.startswith("deepseek"):
        current = remote.startswith(("deepseek-v4", "deepseek-flash", "deepseek-pro"))
        return TextTokenCounter("deepseek_v4" if current else "deepseek_v3", "family")
    try:
        encoding = encoding_name_for_model(remote)
    except KeyError:
        encoding = None
    if encoding in {"cl100k_base", "o200k_base"}:
        return TextTokenCounter(encoding, "model_encoding")
    # Unpublished or unknown vocabularies still get a tokenizer estimate.
    # Provenance explicitly identifies this generic choice, never a byte ratio.
    return TextTokenCounter("qwen", "generic")
