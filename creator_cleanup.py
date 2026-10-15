"""Select stale creator-commerce records and queue their cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai import InfraiClient, InfraiError


RecordKind = Literal[
    "digital_asset_delivery",
    "subscriber_update",
    "content_processing",
]


class CreatorRecord(BaseModel):
    record_id: str = Field(min_length=1)
    kind: RecordKind
    updated_at: datetime
    legal_hold: bool = False


class CleanupSweepRequest(BaseModel):
    sweep_id: str = Field(min_length=1)
    as_of: datetime
    retention_days: int = Field(default=90, ge=1, le=3650)
    records: list[CreatorRecord]


class CleanupSweepResult(BaseModel):
    sweep_id: str
    scanned: int
    queued_record_ids: list[str]
    retained_record_ids: list[str]


class CleanupPublisher(Protocol):
    def publish_cleanup(self, payload: dict[str, str], idempotency_key: str) -> None:
        """Publish one selected cleanup record."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def run_sweep(request: CleanupSweepRequest, publisher: CleanupPublisher) -> CleanupSweepResult:
    cutoff = _utc(request.as_of) - timedelta(days=request.retention_days)
    queued: list[str] = []
    retained: list[str] = []

    for record in request.records:
        stale = _utc(record.updated_at) < cutoff
        if stale and not record.legal_hold:
            publisher.publish_cleanup(
                payload={
                    "sweep_id": request.sweep_id,
                    "record_id": record.record_id,
                    "kind": record.kind,
                    "decision": "delete",
                },
                idempotency_key=f"cleanup:{request.sweep_id}:{record.record_id}",
            )
            queued.append(record.record_id)
        else:
            retained.append(record.record_id)

    return CleanupSweepResult(
        sweep_id=request.sweep_id,
        scanned=len(request.records),
        queued_record_ids=queued,
        retained_record_ids=retained,
    )


app = FastAPI(title="Creator commerce cleanup sweep")


@app.post("/cleanup/sweeps", response_model=CleanupSweepResult)
def sweep(request: CleanupSweepRequest) -> CleanupSweepResult:
    try:
        return run_sweep(request, InfraiClient())
    except InfraiError as error:
        client_status = error.status_code if 400 <= error.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": error.code, "error": dict(error.detail)},
        ) from error


def register_schedule(task_url: str) -> str:
    client = InfraiClient()
    return client.create_cleanup_cron(
        cron_expr="17 3 * * *",
        task=task_url,
        idempotency_key="creator-cleanup-daily-v1",
    )
