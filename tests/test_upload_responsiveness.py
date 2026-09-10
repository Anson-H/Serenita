"""Synchronous upload work must leave the ASGI event loop free to stream."""
import asyncio
import io
import json
from time import perf_counter, sleep
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile
from backend.app.api.body_metrics import preview, upload
from backend.app.api.conversations import upload_context_resource
from backend.app.api.medications import add_source_files


@pytest.mark.parametrize("kind", ["body-image", "body-import", "medication", "conversation"])
def test_upload_processing_does_not_pause_concurrent_stream(kind):
    def process(*args, **kwargs):
        sleep(0.3)  # Deterministic stand-in for signature, disk and database work.
        return {"accepted": True}
    service = SimpleNamespace(attach=process, preview=process, upload=process, add_sources=process,
                              inputs=SimpleNamespace(upload_context_resource=process))
    user = SimpleNamespace(account_id="test")
    file = UploadFile(io.BytesIO(b"test" * 256_000), filename="upload.png")
    async def run():
        if kind == "body-image": operation = upload("member", "record", file, user, service)
        elif kind == "body-import": operation = preview("member", file, "request", "UTC", user, service)
        elif kind == "medication": operation = add_source_files("medication", [file], "request", user, service)
        else: operation = upload_context_resource("member", None, None, file, user, service)
        ticks = []
        task = asyncio.create_task(operation)
        began = perf_counter()
        while not task.done():
            ticks.append(perf_counter())
            await asyncio.sleep(0.01)
        assert await task == {"accepted": True}
        gaps = [b-a for a,b in zip([began, *ticks], [*ticks, perf_counter()])]
        assert len(ticks) >= 5, "upload blocked concurrent stream ticks"
        assert max(gaps) < 0.2
        print(json.dumps({"upload": kind, "stream_ticks": len(ticks), "max_event_loop_delay_ms": round(max(gaps)*1000,2)}))
    asyncio.run(run())
