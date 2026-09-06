import shutil
import subprocess
import tempfile
from pathlib import Path
from backend.app.core.errors import raise_error


def render_source_thumbnail(path: Path, mime_type: str) -> tuple[bytes, str]:
    normalized_mime = {"image/jpg": "image/jpeg", "image/heif": "image/heic"}.get(
        mime_type, mime_type
    )
    if normalized_mime in {"image/jpeg", "image/png"}:
        return path.read_bytes(), normalized_mime

    with tempfile.TemporaryDirectory(prefix="serenita-report-thumbnail-") as directory:
        temporary_root = Path(directory)
        if normalized_mime == "application/pdf":
            converter = shutil.which("pdftoppm")
            if not converter:
                raise_error(
                    "invalid_structure",
                    "REPORT_THUMBNAIL_UNAVAILABLE",
                    "当前环境无法生成 PDF 缩略图。",
                )
            output_prefix = temporary_root / "page"
            command = [
                converter,
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                "-scale-to",
                "1200",
                "-jpeg",
                "-jpegopt",
                "quality=88,progressive=y",
                str(path),
                str(output_prefix),
            ]
            output_path = output_prefix.with_suffix(".jpg")
        elif normalized_mime == "image/heic":
            converter = shutil.which("heif-convert")
            if not converter:
                raise_error(
                    "invalid_structure",
                    "REPORT_THUMBNAIL_UNAVAILABLE",
                    "当前环境无法生成 HEIC 缩略图。",
                )
            output_path = temporary_root / "image.jpg"
            command = [converter, str(path), str(output_path)]
        else:
            raise_error(
                "invalid_structure",
                "REPORT_THUMBNAIL_UNAVAILABLE",
                "该原始文件无法生成缩略图。",
            )

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            content = output_path.read_bytes()
        except (OSError, subprocess.SubprocessError):
            raise_error(
                "invalid_structure",
                "REPORT_THUMBNAIL_UNAVAILABLE",
                "原始文件缩略图生成失败。",
            )
        if not content.startswith(b"\xff\xd8\xff"):
            raise_error(
                "invalid_structure",
                "REPORT_THUMBNAIL_UNAVAILABLE",
                "原始文件缩略图生成失败。",
            )
        return content, "image/jpeg"
