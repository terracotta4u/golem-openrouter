import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterator

import pytest

from golem import JSONSchema, Message, ToolDef, UnsupportedFormat
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
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if not isinstance(body, str) else body.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def test_chat_sends_request_and_maps_tool_call() -> None:
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
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "read", "arguments": '{"path":"foo.go"}'},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    with mock_server(handle) as url:
        msg = OpenRouter("test-key", chat_url=url).chat(
            "openai/gpt-4o-mini",
            [Message(role="user", content="read foo.go")],
            [ToolDef(name="read", description="read a file", parameters={"type": "object"})],
        )

    assert seen["method"] == "POST"
    assert seen["authorization"] == "Bearer test-key"
    assert seen["content_type"] == "application/json"
    assert seen["referer"] == "https://github.com/terracotta4u/golem"
    assert seen["title"] == "golem"
    body = seen["body"]
    assert body["model"] == "openai/gpt-4o-mini"
    assert body["messages"] == [{"role": "user", "content": "read foo.go"}]
    assert body["tools"] == [
        {"type": "function", "function": {"name": "read", "description": "read a file", "parameters": {"type": "object"}}}
    ]
    assert "response_format" not in body
    assert msg.role == "assistant"
    assert len(msg.tool_calls) == 1
    call = msg.tool_calls[0]
    assert call.id == "call_1"
    assert call.function.name == "read"
    assert call.function.arguments == '{"path":"foo.go"}'


def test_chat_structured_sends_json_schema() -> None:
    schema = JSONSchema(
        name="memories",
        strict=True,
        schema={"type": "object", "properties": {"memories": {"type": "array"}}},
    )
    want = {"memories": ["User prefers using uv for projects."]}
    seen: dict[str, Any] = {}

    def handle(handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        seen["body"] = json.loads(raw)
        _write(handler, 200, {"choices": [{"message": {"role": "assistant", "content": json.dumps(want)}}]})

    with mock_server(handle) as url:
        got = OpenRouter("test-key", chat_url=url).chat_structured(
            "openai/gpt-4o-mini",
            [Message(role="user", content="extract")],
            schema,
        )

    body = seen["body"]
    assert body["model"] == "openai/gpt-4o-mini"
    assert body["messages"] == [{"role": "user", "content": "extract"}]
    assert "tools" not in body
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "memories"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["type"] == "object"
    assert got == want


@pytest.mark.parametrize(
    ("status", "body", "unsupported"),
    [
        (400, '{"error":{"message":"This model does not support json_schema response format"}}', True),
        (422, '{"error":{"message":"Invalid response_format"}}', True),
        (400, '{"error":{"message":"structured output is not supported"}}', True),
        (400, '{"error":{"message":"invalid api key"}}', False),
        (500, '{"error":{"message":"json_schema failed internally"}}', False),
    ],
)
def test_chat_structured_unsupported_format(status: int, body: str, unsupported: bool) -> None:
    def handle(handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        _write(handler, status, body.encode())

    with mock_server(handle) as url:
        try:
            OpenRouter("test-key", chat_url=url).chat_structured(
                "openai/gpt-4o-mini",
                [Message(role="user", content="extract")],
                JSONSchema(name="memories"),
            )
        except UnsupportedFormat:
            assert unsupported
        except Exception:
            assert not unsupported
        else:
            raise AssertionError("want error")
