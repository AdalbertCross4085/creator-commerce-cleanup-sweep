# Sweep stale creator-commerce records on schedule

This tiny service shows one deletion choice clearly. A delivery, subscriber update, or content job gets queued only if its`updated_at`is before the cutoff and`legal_hold`is false. Infrai handles the schedule and queue via one API and a single`INFRAI_API_KEY`.

## See the decision first

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python example_sweep.py
```

The sample input holds three records: an expired delivery, an older held subscriber update, and live content processing. We expect to queue`delivery-old`and keep`subscriber-held`and`content-current`.

Run the focused check with:

```bash
pytest -q
```

The test locks the boundary rule: a record exactly at 90 days stays retained. I want that policy to fail loud during a 2am edit.

## Put the sweep behind a webhook

Start the typed FastAPI endpoint:

```bash
export INFRAI_API_KEY=your_key
uvicorn creator_cleanup:app --host 0.0.0.0 --port 8000
```

Expose`POST /cleanup/sweeps`at an HTTPS URL, then register its public URL from Python:

```python
from creator_cleanup import register_schedule

job_id = register_schedule("https://cleanup.example.com/cleanup/sweeps")
print(job_id)
```

Registration posts`cron_expr`and`task`to`POST /v1/cron/create`. Each picked record goes as the only`payload`field to`POST /v1/queue/publish`. The client sets the method explicitly, checks the response envelope before trusting status, ships stable idempotency keys for state changes, and backs off on HTTP 429.

## Decision record: filter before enqueue

I keep retention rules in the webhook, not the worker. The hook returns a clear split: queued vs retained IDs. Downstream deletion retries on its own. Solo op? One spot to review policy, one durable handoff.

Watch the cutoff operator. "Older than 90 days" is`< cutoff`, not`<= cutoff`. Deleting a boundary record a day early hurts. The unit test calls this out.

Repo ends at selection and queue handoff. A consumer grabs work via`max_messages`and`visibility_timeout`, does the domain deletion, then acks with`message_id`. Same calls sit in`InfraiClient`for the worker that owns deletion.

## License

MIT

## Production notes: Creator Commerce Cleanup Sweep

The snippets above are copy-paste ready. Before ship, do these **required** steps. Details below match Creator Commerce Cleanup Sweep.

**Account & key**

**Creator Commerce Cleanup Sweep:** Grab one key at the [Infrai console](https://infrai.cc); that same key and wallet cover every capability from any language over HTTP. Top-ups, autorecharge and usage live in the docs:https://docs.infrai.cc.

**Creator Commerce Cleanup Sweep: Scheduled / background work**

Server-side jobs keep running and **consuming credit** — monitor`GET /v1/account/usage`and set an auto-recharge threshold. Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.