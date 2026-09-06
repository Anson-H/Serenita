from __future__ import annotations

import base64
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


MAX_PDF_PAGES = 30


def model_file_parts(
    path: Path,
    mime_type: str,
    *,
    deadline: float | None = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """Render one local attachment into provider-native content parts."""

    if mime_type != "application/pdf":
        return [
            {
                "type": "image",
                "mime_type": mime_type,
                "name": path.name,
                "data_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        ]
    converter = shutil.which("pdftoppm")
    inspector = shutil.which("pdfinfo")
    if not converter or not inspector:
        raise ValueError("当前环境缺少 PDF 页面检查或渲染组件")
    remaining = deadline - time.monotonic() if deadline is not None else None
    if remaining is not None and remaining <= 0:
        raise TimeoutError("附件预处理超时")
    info_arguments: dict[str, Any] = {
        "check": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if remaining is not None:
        info_arguments["timeout"] = min(10, max(0.001, remaining))
    try:
        info = subprocess.run([inspector, str(path)], **info_arguments)
    except subprocess.CalledProcessError as exc:
        raise ValueError("PDF 文件无法读取或已损坏") from exc
    match = re.search(r"^Pages:\s*(\d+)\s*$", info.stdout, re.MULTILINE)
    if match is None:
        raise ValueError("无法确定 PDF 页数")
    page_count = int(match.group(1))
    if not 1 <= page_count <= MAX_PDF_PAGES:
        raise ValueError(f"PDF 页数必须在 1 到 {MAX_PDF_PAGES} 页之间")
    render_page_limit = (
        min(page_count, max(1, int(max_pages)))
        if max_pages is not None
        else page_count
    )
    with tempfile.TemporaryDirectory(prefix="serenita-attachment-pdf-") as directory:
        output_prefix = Path(directory) / "page"
        remaining = deadline - time.monotonic() if deadline is not None else None
        if remaining is not None and remaining <= 0:
            raise TimeoutError("附件预处理超时")
        render_arguments: dict[str, Any] = {
            "check": True,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
        }
        if remaining is not None:
            render_arguments["timeout"] = min(55, max(0.001, remaining))
        try:
            subprocess.run(
                [
                    converter,
                    "-jpeg",
                    "-r",
                    "144",
                    "-f",
                    "1",
                    "-l",
                    str(render_page_limit),
                    str(path),
                    str(output_prefix),
                ],
                **render_arguments,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError("PDF 页面渲染失败") from exc
        pages = sorted(Path(directory).glob("page-*.jpg"))
        if not pages:
            raise ValueError("PDF 未渲染出可解析页面")
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("附件预处理超时")
        return [
            {
                "type": "image",
                "mime_type": "image/jpeg",
                "name": page.name,
                "data_base64": base64.b64encode(page.read_bytes()).decode("ascii"),
            }
            for page in pages
        ]
