from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import collect, load_config, write_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect validated Berlin events")
    parser.add_argument("--config", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--output", type=Path, default=Path("data/events.json"))
    args = parser.parse_args()
    try:
        events, rejected = collect(load_config(args.config))
        write_events(args.output, events)
    except Exception as exc:
        print(f"collection failed: {exc}", file=sys.stderr)
        return 1
    for message in rejected:
        print(f"rejected: {message}", file=sys.stderr)
    print(f"wrote {len(events)} validated event(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

