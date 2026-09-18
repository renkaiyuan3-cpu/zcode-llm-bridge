#!/usr/bin/env python3
"""把 Grok Build 本地代理注册为 ZCode 自定义 provider（幂等，可重复执行）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_zcode_providers import (  # noqa: E402
    CFG,
    anthropic_reasoning_spec,
    apply_reasoning,
    backup_cfg,
    ensure_provider,
    load_cfg,
    log,
    now_ms,
    save_cfg,
)

META = os.path.expanduser("~/.grokbuild-proxy/data/meta.json")
PROVIDER_ID = "grokbuild-local"


def main() -> None:
    import json
    api_key = json.load(open(META, encoding="utf-8"))["api_key"]
    cfg = load_cfg()
    provider = ensure_provider(cfg, PROVIDER_ID, {
        "name": "Grok Build (订阅)",
        "kind": "anthropic",
        "apiFormat": "anthropic-messages",
        "source": "custom",
        "enabled": True,
        "options": {
            "apiKey": api_key,
            "baseURL": "http://127.0.0.1:8080",
            "apiKeyRequired": True,
        },
    })
    models = provider.setdefault("models", {})
    specs = {
        "grok-4.6": ("Grok 4.6", True),
        "grok-4.5": ("Grok 4.5", False),
    }
    changed = False
    for mid, (name, include_xhigh) in specs.items():
        model = models.setdefault(mid, {
            "name": name,
            "limit": {"context": 500000, "output": 128000},
            "modalities": {"input": ["text"], "output": ["text"]},
            "zcode": {"modified": True},
        })
        model["name"] = name
        model.setdefault("limit", {})["context"] = 500000
        model.setdefault("limit", {})["output"] = 128000
        if apply_reasoning(model, anthropic_reasoning_spec(include_xhigh=include_xhigh)):
            changed = True
    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-grokbuild")
        save_cfg(cfg)
        log("✅ Grok provider 已更新：思考档位写入 reasoning + reasoningSpec + zcode.reasoning", important=True)
        log("   grok-4.6: low/medium/high/xhigh（默认 high）", important=True)
        log("   grok-4.5: low/medium/high（默认 high）", important=True)
    else:
        log("✅ Grok provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
