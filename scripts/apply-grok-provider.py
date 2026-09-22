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
    ensure_option_specs,
    ensure_provider,
    load_cfg,
    log,
    now_ms,
    require_cred,
    save_cfg,
)

META = os.path.expanduser("~/.grokbuild-proxy/data/meta.json")
PROVIDER_ID = "grokbuild-local"


def main() -> None:
    import json
    require_cred(
        META,
        "Grok Build",
        "先安装 grokbuild-proxy 并完成设备码登录（docs/grokbuild-proxy-guide.md / docs/windows-guide.md）。",
    )
    api_key = json.load(open(META, encoding="utf-8"))["api_key"]
    cfg = load_cfg()
    provider, changed = ensure_provider(cfg, PROVIDER_ID, {
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
        "grok-4.7": ("Grok 4.7", True),
        "grok-4.6": ("Grok 4.6", True),
        "grok-4.5": ("Grok 4.5", False),
    }
    model_levels = {}
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
        if mid == "grok-4.7":
            # 4.7 官方支持图像输入（4.5 只有文本）；4.6 已由 ZCode 标记，不动
            model.setdefault("modalities", {})["input"] = ["text", "image"]
            model.setdefault("zcode", {})["modalitiesConfigured"] = True
        spec = anthropic_reasoning_spec(include_xhigh=include_xhigh)
        model_levels[mid] = list(spec["levels"])
        if apply_reasoning(model, spec):
            changed = True
    if ensure_option_specs(PROVIDER_ID, model_levels):
        changed = True
        log("✅ provider_config.json 档位(optionSpecs)已写入 Grok 模型", important=True)
    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-grokbuild")
        save_cfg(cfg)
        log("✅ Grok provider 已更新：思考档位写入 reasoning + reasoningSpec + zcode.reasoning", important=True)
        log("   grok-4.7: low/medium/high/xhigh（默认 high），输入 text+image", important=True)
        log("   grok-4.6: low/medium/high/xhigh（默认 high）", important=True)
        log("   grok-4.5: low/medium/high（默认 high）", important=True)
    else:
        log("✅ Grok provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
