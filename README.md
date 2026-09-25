# golem-openrouter

OpenRouter provider for [Golem](https://github.com/terracotta4u/golem).

## Install 

```bash
golem extension add https://github.com/terracotta4u/golem-openrouter
```

## Setup

Export an API key in the shell that runs Golem, then start the server:

```bash
export OPENROUTER_API_KEY=...
golem serve
```

Restart `golem serve` if it is already running so the extension inherits the key.

## Usage

In the Golem web UI, open **Settings → General**. Choose OpenRouter as the provider, then enter an [OpenRouter model id](https://openrouter.ai/models) for the default and fast models:

```
openai/gpt-6-luna
anthropic/claude-opus-5.5
z-ai/glm-5.3-prime
```