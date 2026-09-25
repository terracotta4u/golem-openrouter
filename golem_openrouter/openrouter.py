import json
import os
import urllib.error
import urllib.request
from typing import Any

from golem import JSONSchema, Message, Provider, ToolDef, UnsupportedFormat

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
REFERER = "https://github.com/terracotta4u/golem"
TITLE = "golem"


class OpenRouter(Provider):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        chat_url: str = CHAT_URL,
        embed_url: str = EMBED_URL,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        key = api_key.strip()
        if not key:
            raise ValueError("set OPENROUTER_API_KEY")
        self.api_key = key
        self.chat_url = chat_url
        self.embed_url = embed_url

    def chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None) -> Message:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
        }
        wrapped = _tools(tools)
        if wrapped:
            payload["tools"] = wrapped
        return self._complete(payload)

    def chat_structured(self, model: str, messages: list[Message], schema: JSONSchema) -> Any:
        msg = self._complete(
            {
                "model": model,
                "messages": [m.to_dict() for m in messages],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.name,
                        "strict": schema.strict,
                        "schema": schema.schema,
                    },
                },
            }
        )
        try:
            return json.loads(msg.content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"openrouter: invalid structured json: {exc}") from exc

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        status, parsed, raw = self._post(self.embed_url, {"model": model, "input": texts})
        err = _error_message(parsed)
        if err:
            raise RuntimeError("openrouter: " + err)
        if status != 200:
            raise RuntimeError(f"openrouter: unexpected status {status}: {raw.decode(errors='replace')}")
        data = parsed.get("data") or []
        if not isinstance(data, list) or not data:
            raise RuntimeError("openrouter: empty embedding response")
        out: list[list[float] | None] = [None] * len(data)
        for item in data:
            if not isinstance(item, dict):
                raise RuntimeError("openrouter: invalid embedding item")
            index = int(item.get("index") or 0)
            if index < 0 or index >= len(out):
                raise RuntimeError(f"openrouter: embedding index {index} out of range")
            vec = item.get("embedding") or []
            if not isinstance(vec, list):
                raise RuntimeError("openrouter: invalid embedding")
            out[index] = [float(v) for v in vec]
        for i, vec in enumerate(out):
            if vec is None:
                raise RuntimeError(f"openrouter: missing embedding for index {i}")
        return out  # type: ignore[return-value]

    def _complete(self, payload: dict[str, Any]) -> Message:
        status, parsed, raw = self._post(self.chat_url, payload)
        err = _error_message(parsed)
        if _unsupported_format(status, err, raw):
            raise UnsupportedFormat(err or raw.decode(errors="replace"))
        if err:
            raise RuntimeError("openrouter: " + err)
        if status != 200:
            raise RuntimeError(f"openrouter: unexpected status {status}: {raw.decode(errors='replace')}")
        choices = parsed.get("choices") or []
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RuntimeError("openrouter: empty response")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise RuntimeError("openrouter: empty response")
        return Message.from_dict(message)

    def _post(self, url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any], bytes]:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "HTTP-Referer": REFERER,
                "X-OpenRouter-Title": TITLE,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=None) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            raise RuntimeError(f"openrouter request: {exc.reason}") from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"decode response: {exc}") from exc
        if not isinstance(parsed, dict):
            parsed = {}
        return status, parsed, raw


def _tools(tools: list[ToolDef] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _error_message(parsed: dict[str, Any]) -> str:
    err = parsed.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "")
    return ""


def _unsupported_format(status: int, err: str, raw: bytes) -> bool:
    if status not in (400, 422):
        return False
    haystack = (err + " " + raw.decode(errors="replace")).lower()
    return "response_format" in haystack or "json_schema" in haystack or "structured output" in haystack
