# golem-openrouter

A Golem provider extension. It registers provider id `openrouter` and answers Golem's chat, structured, and embed callbacks by calling [OpenRouter](https://openrouter.ai). It depends on [`golem-agent-sdk`](https://pypi.org/project/golem-agent-sdk/) (`import golem`).

Golem launches the `golem-openrouter` console script from this package. It injects `GOLEM_URL` and `GOLEM_TOKEN`. The API key comes from `OPENROUTER_API_KEY` in the process environment, or from `~/.golem/etc/conf.json` if you set it there. Golem never receives the key.

## Setup

```sh
export OPENROUTER_API_KEY=...
```

Or set it in `~/.golem/etc/conf.json`:

```json
{
  "extensions": {
    "golem-openrouter": {
      "env": {
        "OPENROUTER_API_KEY": "..."
      }
    }
  }
}
```

An empty conf value does not override a key already in the environment.

## Install

From this directory, after Golem is built:

```sh
golem extension add .
```

Replace an existing install with `--force`. Useful commands:

```sh
golem extension list
golem extension remove golem-openrouter
```

Then start Golem:

```sh
golem serve
```

Disable without uninstalling by setting `"enabled": false` on that conf entry.

## Develop

```sh
uv sync --dev
uv run pytest
```
