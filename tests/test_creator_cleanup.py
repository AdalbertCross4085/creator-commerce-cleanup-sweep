from datetime import datetime, timezone

from creator_cleanup import CleanupSweepRequest, run_sweep


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict[str, str], str]] = []

    def publish_cleanup(self, payload: dict[str, str], idempotency_key: str) -> None:
        self.published.append((payload, idempotency_key))


def test_sweep_queues_only_expired_records_without_a_hold() -> None:
    request = CleanupSweepRequest.model_validate(
        {
            "sweep_id": "sweep-42",
            "as_of": datetime(2026, 9, 4, tzinfo=timezone.utc),
            "retention_days": 90,
            "records": [
                {
                    "record_id": "expired-delivery",
                    "kind": "digital_asset_delivery",
                    "updated_at": "2026-05-01T00:00:00Z",
                },
                {
                    "record_id": "held-subscriber",
                    "kind": "subscriber_update",
                    "updated_at": "2026-04-01T00:00:00Z",
                    "legal_hold": True,
                },
                {
                    "record_id": "cutoff-content",
                    "kind": "content_processing",
                    "updated_at": "2026-06-06T00:00:00Z",
                },
            ],
        }
    )
    publisher = RecordingPublisher()

    result = run_sweep(request, publisher)

    assert result.queued_record_ids == ["expired-delivery"]
    assert result.retained_record_ids == ["held-subscriber", "cutoff-content"]
    assert publisher.published == [
        (
            {
                "sweep_id": "sweep-42",
                "record_id": "expired-delivery",
                "kind": "digital_asset_delivery",
                "decision": "delete",
            },
            "cleanup:sweep-42:expired-delivery",
        )
    ]

