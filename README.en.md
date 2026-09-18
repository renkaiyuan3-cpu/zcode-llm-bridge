<div align="center">

# ZCode LLM Bridge

**Bridge your Grok / Gemini / Codex / DeepSeek subscriptions into [ZCode](https://z.ai):
local proxies · real reasoning levels · self-healing configs via launchd**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-black)](https://github.com/renkaiyuan3-cpu/zcode-llm-bridge)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://github.com/renkaiyuan3-cpu/zcode-llm-bridge)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[简体中文](README.md) | [English](README.en.md)

</div>

---

> [!WARNING]
> This is an **unofficial** community project, not affiliated with xAI, Google, OpenAI, or Z.ai.
> Everything here works against **your own paid subscriptions**. Piping subscription quota
> through unofficial channels may violate the upstream terms of service and can get your
> account rate-limited or banned (similar projects have reported Google enforcement).
> Evaluate the risk yourself. All API keys / OAuth tokens stay on your machine and never
> enter this repository. See [DISCLAIMER.md](DISCLAIMER.md).

## Why this exists

ZCode's custom-provider system is powerful, but wiring CLI subscriptions into it hits four walls — each solved here:

| Problem | Symptom | Solution |
| :--- | :--- | :--- |
| **No subscription channel** | ZCode's built-in Agent CLI only supports GLM (`enabledBuiltinAgentCliProviders = ["glm"]`) | Local proxies (CLIProxyAPI / grokbuild-proxy) turn subscription OAuth into standard OpenAI / Anthropic protocols |
| **Fake reasoning UI** | You configure Low/Medium/High in the UI, but a packet capture shows **no `thinking` field at all** in the request | Reverse-engineered `reasoningSpec` injection (see the [Chinese README §2](README.md#2-核心技术突破zcode-思考模式reasoning深度逆向)), including the second variant: levels whose values the upstream rejects |
| **Config wiped on restart** | ZCode quietly strips top-level `reasoningSpec` when it rewrites its config | A `com.zcode.restore-reasoning` launchd job re-applies the patch every 60 s, idempotently |
| **Credential kicking** | Subscription OAuth refresh tokens rotate on use, so sharing them between clients logs the other one out | Independent device-flow authorization per channel with isolated credential stores |

**5 channels**: Grok Build (local proxy :8080, Anthropic protocol), Antigravity Gemini (CLIProxyAPI :8317, Anthropic), Codex / ChatGPT subscription (CLIProxyAPI :8327, OpenAI-compatible), OpenCode Go (direct API, DeepSeek V4.1 Flash), Command Code (direct API, DeepSeek + GPT-5.6 Luna). Full comparison table in the [Chinese README](README.md#1-整体架构与模型对照).

## Quick start

> Prerequisites: macOS, the [ZCode](https://z.ai) client, `python3`. Make sure ZCode has been launched at least once — the injection scripts write into `~/.zcode/v2/config.json`, which ZCode creates on first start.

```bash
git clone https://github.com/renkaiyuan3-cpu/zcode-llm-bridge.git
cd zcode-llm-bridge
```

**Gemini (Antigravity subscription)** — install [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) to `~/.cliproxyapi/cli-proxy-api`, then:

```bash
mkdir -p ~/.cliproxyapi
cp ~/Downloads/cli-proxy-api-darwin-arm64 ~/.cliproxyapi/cli-proxy-api && chmod +x ~/.cliproxyapi/cli-proxy-api
cp templates/cliproxyapi-gemini.example.yaml ~/.cliproxyapi/config.yaml
cd ~/.cliproxyapi && ./cli-proxy-api -config config.yaml -antigravity-login && cd -
./launchd/install-launchd.sh gemini
python3 scripts/apply-gemini-provider.py
```

**Codex (ChatGPT subscription)** — same binary, isolated instance on port 8327:

```bash
cp templates/cliproxyapi-codex.example.yaml ~/.cliproxyapi/config-codex.yaml
# Import the flattened OAuth credentials: docs/codex-guide.md §4 (Chinese)
./launchd/install-launchd.sh codex
python3 scripts/apply-codex-provider.py
```

**Grok Build** — independent device-flow login, isolated from the official Grok CLI:

```bash
# Get the binary (Releases or `go build`): docs/grokbuild-proxy-guide.md §1.1 (Chinese)
mkdir -p ~/.grokbuild-proxy
cp templates/grokbuild-proxy.example.yaml ~/.grokbuild-proxy/config.yaml
cd ~/.grokbuild-proxy && ./grokbuild-proxy -device-login && cd -
./launchd/install-launchd.sh grok
python3 scripts/apply-grok-provider.py
```

**OpenCode Go / Command Code (direct API, no proxy)**:

```bash
mkdir -p ~/.commandcode && echo "sk-your-key" > ~/.commandcode/api_key
python3 scripts/apply-commandcode-provider.py
# OpenCode Go: ~/.opencode-go/api_key + scripts/apply-opencode-go-provider.py
```

**Last step (required)** — install the reasoning self-healing job, then restart ZCode:

```bash
./launchd/install-launchd.sh restore
./scripts/service-manager.sh status   # health check
```

**Verify (5 min)**: ① `service-manager.sh status` shows all proxy ports listening and `/v1/models` returning 200 with models; ② after restarting ZCode, the model picker shows the new providers (`Grok Build (订阅)`, `Antigravity (Gemini)`, `Codex`, …); ③ send a message with a new model and watch it hit the local proxy log; ④ send the same reasoning question at `Low` vs `High` — High should visibly think longer (if not, the `reasoningSpec` patch was stripped; see the self-healing checks in the [Chinese README §6](README.md#6-日常运维与故障排除速查手册)).

## What's inside

```
┌──────────────────────────────────────────────────────────────┐
│                    ZCode client (~/.zcode/v2/config.json)    │
└──┬──────────────┬──────────────┬──────────────┬──────────────┘
   │ :8080        │ :8317        │ :8327        │ HTTPS (direct)
   ▼              ▼              ▼              ▼
 grokbuild-     CLIProxyAPI    CLIProxyAPI    opencode.ai / api.commandcode.ai
 proxy          (Gemini)       (Codex)        (OpenCode Go / Command Code)
   ▼              ▼              ▼
 cli-chat-proxy.cloudcode-pa.  chatgpt.com/backend-api/codex
 .grok.com     googleapis.com
```

- `scripts/` — idempotent one-shot scripts that register each provider into `~/.zcode/v2/config.json`, injecting **both** the UI reasoning variants and the real `reasoningSpec` patch (Anthropic `thinking.budgetTokens` / OpenAI `reasoning_effort`).
- `scripts/lib_zcode_providers.py` — shared spec builders; the patch is written to three locations (`reasoning`, `reasoningSpec`, `zcode.reasoning`) so it survives ZCode's config rewrite.
- `launchd/` — plist templates (`__HOME__` placeholder) + `install-launchd.sh` renderer. The self-healing job re-applies reasoning patches every 60 s.
- `docs/` — deep-dive guides per provider (Chinese), including the reverse-engineering notes and every pitfall we hit: flattened Codex credentials, rejected `ultra` level, the missing `off` level, the 272K pricing cliff on Codex 1M context, macOS TCC blocking launchd on `~/Desktop`, and more.
- `templates/` — sanitized example configs. No real credentials, ever.

## Hard-won gotchas (highlights)

- **Codex credentials must be flattened + `type: "codex"`** — copying `~/.codex/auth.json` verbatim fails *silently*: logs show `1 auth entries` but `/v1/models` returns 0 models.
- **Level domains differ per provider.** Codex's model catalog advertises 6 levels but CPA rejects `ultra` (valid: `low/medium/high/xhigh/max`). Command Code rejects `off`/`none` with HTTP 400. Never copy another provider's level list.
- **Codex speed tiers (`service_tier: priority`) are account-gated** — verified by hitting the ChatGPT backend directly; the echo is always `default` on Plus. Not exposed here, because a level that never works is worse than none.
- **Codex 1M context works** (default 272K is just the conservative default; official docs say 1,050,000) — but input over 272K triggers **2x/1.5x pricing on the entire request**.
- **macOS TCC silently kills launchd jobs reading `~/Desktop`** (`Operation not permitted`); that's why runtime copies live in `~/.zcode-proxy/`.

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the "add a new provider" recipe (protocol choice, level-domain verification checklist, launchd registration).

## Credits & License

Built on the shoulders of [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) and [GreyGunG/grokbuild-proxy](https://github.com/GreyGunG/grokbuild-proxy); inspired by [claude-code-router](https://github.com/musistudio/claude-code-router), [antigravity-claude-proxy](https://github.com/badrisnarayanan/antigravity-claude-proxy) and [copilot-api](https://github.com/ericc-ch/copilot-api).

Code is released under the [MIT License](LICENSE). The license covers the code in this repository only — **not** your usage of it against upstream terms of service. See [DISCLAIMER.md](DISCLAIMER.md).
