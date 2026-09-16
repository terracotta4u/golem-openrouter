import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterator

from golem_openrouter.openrouter import OpenRouter


@contextmanager
def mock_server(handle: Callable[[BaseHTTPRequestHandler, bytes], None]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            handle(self, raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _write(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def test_embed_sends_request_and_maps_vectors() -> None:
    seen: dict[str, Any] = {}

    def handle(handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        seen["method"] = handler.command
        seen["authorization"] = handler.headers.get("Authorization")
        seen["content_type"] = handler.headers.get("Content-Type")
        seen["referer"] = handler.headers.get("HTTP-Referer")
        seen["title"] = handler.headers.get("X-OpenRouter-Title")
        seen["body"] = json.loads(raw)
        _write(
            handler,
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0.5, 0.75]},
                    {"index": 0, "embedding": [0.25, 0.5]},
                ]
            },
        )

    with mock_server(handle) as url:
        got = OpenRouter("test-key", embed_url=url).embed(
            "openai/text-embedding-3-small",
            ["hello", "world"],
        )

    assert seen["method"] == "POST"
    assert seen["authorization"] == "Bearer test-key"
    assert seen["content_type"] == "application/json"
    assert seen["referer"] == "https://github.com/terracotta4u/golem"
    assert seen["title"] == "golem"
    body = seen["body"]
    assert body["model"] == "openai/text-embedding-3-small"
    assert body["input"] == ["hello", "world"]
    assert got == [[0.25, 0.5], [0.5, 0.75]]


def test_embed_api_error() -> None:
    def handle(handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        _write(handler, 200, {"error": {"message": "nope"}})

    with mock_server(handle) as url:
        try:
            OpenRouter("test-key", embed_url=url).embed("openai/text-embedding-3-small", ["hello"])
        except Exception as exc:
            assert "nope" in str(exc)
        else:
            raise AssertionError("want error")
