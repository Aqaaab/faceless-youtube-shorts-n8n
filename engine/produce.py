from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automotive Content Engine")
    parser.add_argument("--topic", required=True, help="Car or automotive topic")
    parser.add_argument("--dry-run", action="store_true", help="Validate orchestration without external providers")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.topic.strip():
        raise SystemExit("Topic must not be empty")
    # Production stages are added incrementally. Keeping this command stable from
    # Phase 1 gives every later stage one canonical entry point.
    print(f"AUTOMOTIVE_ENGINE topic={args.topic.strip()} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
