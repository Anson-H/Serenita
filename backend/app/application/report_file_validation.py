from __future__ import annotations


REPORT_SIGNATURE_ERROR = "文件内容与扩展名不匹配。"


def validate_report_signature(content: bytes, expected_mime_type: str) -> None:
    """Reject a report whose bytes do not match its allow-listed media type."""

    if expected_mime_type == "image/jpeg":
        valid = len(content) >= 3 and content[:3] == b"\xff\xd8\xff"
    elif expected_mime_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif expected_mime_type == "application/pdf":
        valid = content.startswith(b"%PDF-")
    elif expected_mime_type == "image/heic":
        valid = _is_heic(content)
    else:
        valid = False
    if not valid:
        raise ValueError(REPORT_SIGNATURE_ERROR)


def _is_heic(content: bytes) -> bool:
    if len(content) < 12 or content[4:8] != b"ftyp":
        return False
    brand_offset = 8
    box_size = int.from_bytes(content[:4], "big")
    if box_size == 0:
        box_end = len(content)
    elif box_size == 1:
        if len(content) < 24:
            return False
        box_end = min(len(content), int.from_bytes(content[8:16], "big"))
        brand_offset = 16
    else:
        box_end = min(len(content), box_size)
    if box_end < brand_offset + 4:
        return False
    brands = {
        content[offset : offset + 4]
        for offset in range(brand_offset, box_end - 3, 4)
    }
    return bool(brands & {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1"})
