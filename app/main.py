from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import GenerateRequest
from app.services.catalog import CatalogService
from app.services.pipeline import DoppelPipeline

app = FastAPI(
    title="DOPPEL",
    description="Metadata-governed synthetic data products powered by DataHub",
    version="0.1.0",
)
pipeline = DoppelPipeline()
catalog = CatalogService()
static_dir = Path(__file__).parent / "static"


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": settings.doppel_mode,
        "datahub": settings.datahub_gms_url if settings.live_datahub else "fixture",
    }


@app.get("/api/assets")
def list_assets() -> list[dict[str, object]]:
    return [asset.model_dump() for asset in catalog.list_assets()]


@app.get("/api/assets/{asset_id}")
def get_asset(asset_id: str) -> dict[str, object]:
    try:
        asset = catalog.get_asset(asset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    previews: dict[str, list[dict[str, object]]] = {}
    row_counts: dict[str, int] = {}
    asset_dir = settings.doppel_data_dir / asset_id
    for table in asset.tables:
        frame = pd.read_csv(asset_dir / table.file)
        previews[table.name] = frame.head(8).fillna("").to_dict(orient="records")
        row_counts[table.name] = len(frame)
    payload = asset.model_dump()
    payload["previews"] = previews
    payload["row_counts"] = row_counts
    return payload


@app.post("/api/runs")
def create_run(request: GenerateRequest) -> dict[str, object]:
    try:
        return pipeline.generate(request).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


_stream_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="doppel-sse-")


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/api/runs/stream")
async def create_run_stream(request: GenerateRequest) -> StreamingResponse:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    report_holder: dict[str, Any] = {}

    def event_callback(stage: str, status: str, message: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "stage", "stage": stage, "status": status, "message": message},
        )

    def run_pipeline() -> None:
        try:
            report = pipeline.generate(request, event_callback=event_callback)
            report_holder["report"] = report.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": str(exc)},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def stream() -> AsyncIterator[str]:
        task = loop.run_in_executor(_stream_executor, run_pipeline)
        while True:
            event = await queue.get()
            if event is None:
                report = report_holder.get("report")
                if report:
                    yield _sse_event({"type": "complete", "report": report})
                else:
                    yield _sse_event({"type": "complete"})
                break
            yield _sse_event(event)
        await task

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/runs")
def list_runs() -> list[dict[str, object]]:
    return [report.model_dump(mode="json") for report in pipeline.list_runs()]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    try:
        return pipeline.get_report(run_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(404, f"Unknown run: {run_id}") from exc


@app.post("/api/runs/{run_id}/publish")
def publish_run(run_id: str) -> dict[str, object]:
    try:
        return pipeline.publish(run_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(404, f"Unknown run: {run_id}") from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    try:
        pipeline.delete(run_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown run: {run_id}") from exc


@app.get("/api/runs/{run_id}/download")
def download_run(run_id: str) -> FileResponse:
    try:
        report = pipeline.get_report(run_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown run: {run_id}") from exc
    bundle = Path(report.output_dir, f"doppel-{run_id}.zip")
    if not bundle.exists():
        bundle = pipeline._build_bundle(report)
    return FileResponse(bundle, filename=bundle.name, media_type="application/zip")


@app.get("/api/runs/{run_id}/datahub-preview")
def datahub_preview(run_id: str) -> FileResponse:
    try:
        report = pipeline.get_report(run_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown run: {run_id}") from exc
    preview = Path(report.output_dir, "datahub-mutation-preview.json")
    if not preview.exists():
        raise HTTPException(404, "No DataHub mutation preview for this run.")
    return FileResponse(preview, filename=preview.name, media_type="application/json")


app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
