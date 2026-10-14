"""Command line helpers for local testing.

Examples
--------
``python -m compliance.cli serve --port 8099``
``python -m compliance.cli acknowledge --request-id REQ-DEMO --actor THG4SZH``
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import DEFAULT_STORAGE, DEFAULT_TEMPLATE, ComplianceService
from .server import main as serve_main


def _service(args) -> ComplianceService:
    return ComplianceService(
        storage_dir=Path(args.storage), template_path=Path(args.template)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compliance", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8099)

    ack = sub.add_parser("acknowledge", help="simulate ticking the frontend checkbox")
    ack.add_argument("--request-id", required=True)
    ack.add_argument("--actor", default=None)
    ack.add_argument("--name", default=None, help="IT-solution name for the Completion Record")
    ack.add_argument("--storage-location", default=None)
    ack.add_argument("--sign-off", default=None)
    ack.add_argument("--force", action="store_true", help="regenerate an existing document")
    ack.add_argument("--revoke", action="store_true", help="clear the checkbox instead")

    for sub_parser in (serve, ack):
        sub_parser.add_argument("--storage", default=str(DEFAULT_STORAGE))
        sub_parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
        sub_parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "serve":
        forwarded = ["--host", args.host, "--port", str(args.port)]
        forwarded += ["--storage", args.storage, "--template", args.template]
        if args.verbose:
            forwarded.append("--verbose")
        return serve_main(forwarded)

    state = _service(args).acknowledge(
        args.request_id,
        acknowledged=not args.revoke,
        actor=args.actor,
        name=args.name,
        storage_location=args.storage_location,
        sign_off=args.sign_off,
        force=args.force,
    )
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
