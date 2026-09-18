#!/usr/bin/env python3
"""把 OpenCode Go 订阅接到 ZCode，只暴露 DeepSeek V4.1 Flash。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_zcode_providers import (  # noqa: E402
    CFG,
    apply_reasoning,
    backup_cfg,
    ensure_provider,
    load_cfg,
    log,
    now_ms,
    openai_reasoning_spec,
    save_cfg,
)

PROVIDER_ID = "opencode-go"
API_KEY_FILE = os.path.expanduser("~/.opencode-go/api_key")
MODEL_ID = "deepseek-v4.1-flash"
VARIANTS = ["off", "low", "medium", "high", "xhigh", "max"]


def load_api_key() -> str:
    env = os.environ.get("OPENCODE_GO_API_KEY", "").strip()
    if env:
        return env
    if os.path.isfile(API_KEY_FILE):
        return open(API_KEY_FILE, encoding="utf-8").read().strip()
    raise SystemExit(
        "缺少 OpenCode Go API Key。请写入 ~/.opencode-go/api_key，"
        "或设置环境变量 OPENCODE_GO_API_KEY 后再跑本脚本。"
    )


def persist_api_key(key: str) -> None:
    directory = os.path.dirname(API_KEY_FILE)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd = os.open(API_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key + "\n")


def main() -> None:
    api_key = load_api_key()
    if not api_key:
        raise SystemExit("缺少 OpenCode Go API Key")
    persist_api_key(api_key)
    cfg = load_cfg()
    provider = ensure_provider(cfg, PROVIDER_ID, {
        "name": "OpenCode Go",
        "kind": "openai-compatible",
        "apiFormat": "openai-chat-completions",
        "source": "custom",
        "enabled": True,
        "options": {
            "apiKey": api_key,
            "baseURL": "https://opencode.ai/zen/go/v1",
            "apiKeyRequired": True,
        },
        "headers": {
            "User-Agent": "ZCode",
            "x-opencode-session": "zcode-opencode-go-local",
        },
    })
    models = provider.setdefault("models", {})
    for mid in list(models):
        if mid != MODEL_ID:
            del models[mid]
    model = models.setdefault(MODEL_ID, {
        "name": "DeepSeek V4.1 Flash",
        "limit": {"context": 1000000, "output": 128000},
        "modalities": {"input": ["text"], "output": ["text"]},
        "zcode": {"modified": True},
    })
    model["name"] = "DeepSeek V4.1 Flash"
    model.setdefault("limit", {})["context"] = 1000000
    model.setdefault("limit", {})["output"] = 128000
    changed = apply_reasoning(model, openai_reasoning_spec(VARIANTS, default="high"))
    zcode = provider.setdefault("zcode", {})
    tombstones = [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-flash",
        "deepseek-v4-flash-vision-exp",
        "glm-5.3",
        "glm-5.3-flash",
        "kimi-k3",
        "kimi-k2.7-code",
    ]
    if zcode.get("deletedModels") != tombstones:
        zcode["deletedModels"] = tombstones
        changed = True
    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-opencode-go")
        save_cfg(cfg)
        log("✅ OpenCode Go 已接入：仅 DeepSeek V4.1 Flash", important=True)
        log("   endpoint: https://opencode.ai/zen/go/v1/chat/completions", important=True)
        log("   model:    deepseek-v4.1-flash", important=True)
        log("   档位:     off/low/medium/high/xhigh/max（默认 high，对应 reasoning_effort）", important=True)
    else:
        log("✅ OpenCode Go provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
