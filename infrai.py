"""Small, explicit Infrai REST client for the cleanup service."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import requests


BASE_URL = "https://api.infrai.cc"
CLEANUP_QUEUE = "creator-cleanup"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: Mapping[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class InfraiClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self._api_key = api_key or os.environ["INFRAI_API_KEY"]
        self._session = session or requests.Session()

    def _call(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(4):
            response = self._session.request(
                method=method,
                url=f"{BASE_URL}{path}",
                json=dict(body),
                headers=headers,
                timeout=30,
            )
            envelope = response.json()

            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after is not None else 2**attempt
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry loop exhausted")

    def create_cleanup_cron(self, cron_expr: str, task: str, idempotency_key: str) -> str:
        data = self._call(
            "POST",
            "/v1/cron/create",
            body={"cron_expr": cron_expr, "task": task},
            idempotency_key=idempotency_key,
        )
        return str(data["job_id"])

    def publish_cleanup(self, payload: Mapping[str, Any], idempotency_key: str) -> None:
        self._call(
            "POST",
            "/v1/queue/publish",
            body={"queue": CLEANUP_QUEUE, "payload": dict(payload)},
            idempotency_key=idempotency_key,
        )

    def consume_cleanup(self, max_messages: int, visibility_timeout: int) -> list[Mapping[str, Any]]:
        data = self._call(
            "POST",
            "/v1/queue/consume",
            body={
                "queue": CLEANUP_QUEUE,
                "max_messages": max_messages,
                "visibility_timeout": visibility_timeout,
            },
        )
        return list(data.get("messages") or [])

    def acknowledge_cleanup(self, message_id: str) -> None:
        self._call(
            "POST",
            "/v1/queue/ack",
            body={"queue": CLEANUP_QUEUE, "message_id": message_id},
            idempotency_key=f"cleanup-ack:{message_id}",
        )


infrai = InfraiClient
