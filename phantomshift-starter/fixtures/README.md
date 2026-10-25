# Fixtures

`samples/` holds synthetic "invoice arrived" events (JSON). `inbox/` is what `python3 -m phantomshift watch` polls.
Copy a sample into `inbox/` while the watcher runs and the full pipeline starts with nobody prompting it:

    cp fixtures/samples/invoice_redirect.json fixtures/inbox/
    cp fixtures/samples/ticket_exfil.json fixtures/inbox/

The watcher dedupes by file content hash, retries with backoff, and records every step in the event store
(`artifacts/events.sqlite`). This is a polling loop over a local directory, NOT an OpenClaw agent (gate H01 stays NOT TESTED).
All content is synthetic.
