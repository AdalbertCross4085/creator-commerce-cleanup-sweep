"""Run the business decision locally without calling an external service."""

from datetime import datetime, timezone

from creator_cleanup import CleanupSweepRequest, run_sweep


class PrintingPublisher:
    def publish_cleanup(self, payload: dict[str, str], idempotency_key: str) -> None:
        print("queued", payload, "idempotency_key=", idempotency_key)


request = CleanupSweepRequest.model_validate(
    {
        "sweep_id": "sweep-2026-09-04",
        "as_of": datetime(2026, 9, 4, tzinfo=timezone.utc),
        "retention_days": 90,
        "records": [
            {
                "record_id": "delivery-old",
                "kind": "digital_asset_delivery",
                "updated_at": "2026-05-01T00:00:00Z",
            },
            {
                "record_id": "subscriber-held",
                "kind": "subscriber_update",
                "updated_at": "2026-04-01T00:00:00Z",
                "legal_hold": True,
            },
            {
                "record_id": "content-current",
                "kind": "content_processing",
                "updated_at": "2026-08-30T00:00:00Z",
            },
        ],
    }
)

print(run_sweep(request, PrintingPublisher()).model_dump_json(indent=2))

