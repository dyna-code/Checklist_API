"""Standard-library HTTP API for the checklist backend.

Routes
------
``POST /api/ai-requests/{id}/compliance/acknowledge``
    Body ``{"termsAcknowledged": true, "actor": "THG4SZH"}``. Flips every
    checklist question to "Yes" and generates the DOCX.
``GET  /api/ai-requests/{id}/compliance``
    Current acknowledgement state.
``GET  /api/ai-requests/{id}/compliance/checklist.docx``
    The generated document.
``GET  /healthz``
    Liveness probe.

Only the Python standard library is used, so the service runs with the
bundled interpreter and no extra installs.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .service import (
    DEFAULT_STORAGE,
    DEFAULT_TEMPLATE,
    ComplianceService,
    InvalidRequestId,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _optional_str(value, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


class ChecklistRequestHandler(BaseHTTPRequestHandler):
    server_version = "ChecklistBackend/1.0"
    protocol_version = "HTTP/1.1"
    service: ComplianceService  # injected by create_server()

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        if self.server.verbose:  # type: ignore[attr-defined]
            super().log_message(fmt, *args)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _cors(self) -> None:
        # The portal runs on another origin, so the browser needs these.
        # Restrict Access-Control-Allow-Origin to the portal host in production.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Actor")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    # -- routing ----------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        segments = [unquote(part) for part in urlparse(self.path).path.split("/") if part]

        if segments == ["healthz"]:
            self._json(200, {"status": "ok"})
            return

        if len(segments) < 3 or segments[:2] != ["api", "ai-requests"]:
            self._json(404, {"error": "not found", "path": self.path})
            return

        request_id = segments[2]
        tail = segments[3:]

        try:
            if tail == ["compliance"] and method == "GET":
                state = self.service.get_state(request_id) or self.service.default_state(
                    request_id
                )
                self._json(200, state)
                return

            if tail == ["compliance", "acknowledge"] and method == "POST":
                body = self._read_json()
                actor = body.get("actor") or self.headers.get("X-Actor")
                acknowledged = body.get("termsAcknowledged", True)
                if not isinstance(acknowledged, bool):
                    raise ValueError("termsAcknowledged must be a boolean")
                state = self.service.acknowledge(
                    request_id,
                    acknowledged=acknowledged,
                    actor=_optional_str(actor, "actor"),
                    name=_optional_str(body.get("name"), "name"),
                    storage_location=_optional_str(
                        body.get("storageLocation"), "storageLocation"
                    ),
                    sign_off=_optional_str(body.get("signOff"), "signOff"),
                    force=bool(body.get("force", False)),
                )
                payload = dict(state)
                if state.get("termsAcknowledged"):
                    payload["documentUrl"] = (
                        f"/api/ai-requests/{request_id}/compliance/checklist.docx"
                    )
                self._json(200, payload)
                return

            if tail == ["compliance", "checklist.docx"] and method == "GET":
                path = self.service.document_path(request_id)
                if not path.is_file():
                    self._json(
                        404,
                        {
                            "error": "no document generated",
                            "requestId": request_id,
                            "hint": "POST .../compliance/acknowledge first",
                        },
                    )
                    return
                body = path.read_bytes()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", DOCX_MIME)
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{path.name}"'
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self._json(404, {"error": "not found", "path": self.path})
        except InvalidRequestId as exc:
            self._json(400, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})


def create_server(
    service: ComplianceService,
    *,
    host: str = "127.0.0.1",
    port: int = 8099,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    handler = type("BoundChecklistHandler", (ChecklistRequestHandler,), {"service": service})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.verbose = verbose  # type: ignore[attr-defined]
    return httpd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="China AI compliance checklist backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--storage", default=str(DEFAULT_STORAGE))
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    service = ComplianceService(
        storage_dir=Path(args.storage), template_path=Path(args.template)
    )
    httpd = create_server(service, host=args.host, port=args.port, verbose=args.verbose)
    print(f"checklist backend listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
