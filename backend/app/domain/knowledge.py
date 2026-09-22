"""Knowledge text segmentation and language-independent lexical search terms."""

from collections import Counter
import re
import unicodedata


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARACTERS = 1_000_000
SEGMENT_CHARACTERS = 2000
MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def search_terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = []
    for word in re.findall(r"[\u3400-\u9fff]+|[^\W_]+", normalized):
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            terms.extend(word[i:i + 2] for i in range(len(word) - 1))
            if len(word) == 1:
                terms.append(word)
        else:
            terms.append(word)
    return Counter(terms)


def segment_pages(pages):
    segments = []
    for page_number, text in pages:
        offset = 0
        while offset < len(text):
            end = min(offset + SEGMENT_CHARACTERS, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", offset + SEGMENT_CHARACTERS // 2, end),
                               text.rfind("。", offset + SEGMENT_CHARACTERS // 2, end))
                if boundary >= 0:
                    end = boundary + 1
            content = text[offset:end].strip()
            if content:
                segments.append({"segment_index": len(segments) + 1, "page_number": page_number, "content": content})
            offset = end
    return segments
