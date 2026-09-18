# Berlin Events Bot

A small Python pipeline that collects Berlin events from explicitly approved APIs,
rejects incomplete records, deduplicates them, and writes stable JSON for consumers
such as TaxiSpot Berlin.

The repository deliberately ships with **no live event source enabled**. No events
are invented, and a source should only be added to `config/sources.json` after its
API documentation and terms of use have been reviewed.

## Requirements

- Python 3.11+
- An API endpoint and field mapping supplied by the source owner/documentation
- Any required API secret stored as an environment variable or GitHub secret

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m berlin_events --config config/sources.json --output data/events.json
```

With the default empty configuration, the command safely writes an empty event
collection. It does not contact the internet.

## Adding the first API

Copy the object in `config/sources.example.json` into the `sources` array in
`config/sources.json`, then replace every placeholder using the API's official
documentation. The generic adapter supports dotted paths such as `venue.name`.

Required normalized values are:

- a non-empty source event ID;
- title;
- date and time (ISO 8601, including a UTC offset or `Z`);
- a clear venue name and/or street address;
- city equal to Berlin (case-insensitive).

Secrets are referenced by variable name (`api_key_env`), never by value. Locally,
set that environment variable outside the repository. On GitHub, add it under
**Settings → Secrets and variables → Actions → New repository secret**.

Before enabling a source, record its official documentation and terms URL in the
config and confirm that automated retrieval, storage, redistribution, polling every
six hours, and attribution (if required) are permitted. This project does not make
that legal/contractual decision automatically.

## Deduplication

Events from the same source are identified by `(source, source_id)`. Across sources,
the fallback key is a normalized combination of title, start time, and place. Both
the venue and address are considered. When duplicates are merged, source references
are retained in `source_refs`; existing non-empty data is never replaced by an empty
value.

## Output contract

`data/events.json` contains a UTC generation timestamp, count, and an `events` array.
A collection failure exits non-zero before writing the output. Invalid individual
records are rejected and summarized on standard error.

## GitHub Actions

The workflow in `.github/workflows/update-events.yml` runs every six hours and can
also be started manually. To use it:

1. Create a Git repository inside this folder and commit the files.
2. Create an empty GitHub repository and add it as `origin`; this project does not
   assume one already exists.
3. Configure the source and add its API-key secret, if applicable.
4. Push the default branch and grant Actions **Read and write permissions** under
   repository Settings → Actions → General → Workflow permissions.

The workflow tests first, updates the JSON, and commits only when the file changed.
GitHub cron schedules may be delayed during load; six hours is the requested cadence,
not a real-time guarantee.
