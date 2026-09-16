import os
import sys

from golem import Extension, GolemError
from golem_openrouter.openrouter import OpenRouter

__all__ = ["OpenRouter", "main", "run"]


def main() -> None:
    try:
        run()
    except (GolemError, ValueError) as exc:
        print(exc, file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


def run() -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("set OPENROUTER_API_KEY")
    Extension.from_env("golem-openrouter").provider("openrouter", OpenRouter(key)).run()
