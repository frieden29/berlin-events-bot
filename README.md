# Berlin Events Bot

A small Python pipeline that collects Berlin events from explicitly approved APIs,
rejects incomplete records, deduplicates them, and writes stable JSON for consumers
such as TaxiSpot Berlin.

Ticketmaster Discovery v2 is configured in `config/sources.json`. Its key must be
provided through the environment. Tests use synthetic records and mocked HTTP only.

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
python -m berlin_events --config config/sources.json --output runtime/events.json
```

Without `BERLIN_EVENTS_API_KEY`, collection fails before contacting the API.
Windows installations include `tzdata` for `Europe/Berlin` timezone conversion.

## Adding other APIs

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

`runtime/events.json` contains a UTC generation timestamp, count, and an `events` array.
Events include optional `latitude` and `longitude`. `runtime/` is ignored by Git;
`data/events.json` remains an empty placeholder, not the live output.
A collection failure exits non-zero before writing the output. Invalid individual
records are rejected and summarized on standard error.

## GitHub Actions

The workflow in `.github/workflows/update-events.yml` runs every six hours and can
also be started manually. To use it:

1. Create a Git repository inside this folder and commit the files.
2. Create an empty GitHub repository and add it as `origin`; this project does not
   assume one already exists.
3. Add the repository Actions secret `BERLIN_EVENTS_API_KEY`.
4. Push the default branch. The workflow only needs read access to repository contents.

The workflow tests first, collects JSON, and uploads a `berlin-events` artifact with
one-day retention. Live content is never committed to permanent Git history.
GitHub cron schedules may be delayed during load; six hours is the requested cadence,
not a real-time guarantee.

## Ticketmaster specifics and terms review (2026-09-18)

Official documentation: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/

Terms: https://developer.ticketmaster.com/support/terms-of-use/

GET `https://app.ticketmaster.com/discovery/v2/events.json` uses `city=Berlin`,
`countryCode=DE`, and the runtime **query parameter `apikey`**, not Bearer auth.
The workflow maps `secrets.BERLIN_EVENTS_API_KEY` to that environment variable.
The generic `sources.example.json` is for other APIs; its header auth is not used
by the dedicated Ticketmaster adapter.

Mapping: `id`, `name`, `url`, `dates.start.dateTime`, and `_embedded.venues[0]`
(name/address/city/country/location). Times are converted to Europe/Berlin, preserving
the local calendar date. Explicit localDate/localTime/timezone can be used if UTC
is absent; ambiguous/nonexistent DST times, missing places, TBA/TBD, unspecified
times, cancelled/postponed events and conflicting dates are rejected.

Default published limits are 5,000 calls/day and 5 calls/second, with deep paging
restricted to `size * page < 1000`. The collector uses at most five 200-event pages,
one second apart (at most 20 calls/day at the configured schedule). It stops on 429
or exhausted response quota without retrying. Account-wide usage by other apps or
manual runs counts too. More than 1,000 results fails explicitly, preserving the old
output; narrow the `startDateTime`/`endDateTime` query range if necessary.

Terms restrict caching to reasonable service periods and require removal within
24 hours of an owner's request. They also restrict revenue-generating API use:
commercial TaxiSpot use needs confirmation of applicable Ticketmaster permission.
`terms_reviewed` records a technical review, not commercial permission. Keep source
attribution and event links in consumers and do not replicate the ticketing service.

Local snapshots must be deleted within 24 hours, including stale files after failed
refreshes. Honor removal requests by deleting affected artifacts and downstream
copies promptly. Artifact expiry alone does not handle removal requests. Never
commit live snapshots or API keys. Redirects are refused and request errors omit
credential-bearing URLs, raw response bodies and underlying exception text.
