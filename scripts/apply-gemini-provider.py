#!/usr/bin/env python3
"""把 Antigravity(Gemini) 接入 ZCode —— 只保留当前使用的 3 个模型。幂等。"""
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

KEYS = os.path.expanduser("~/.cliproxyapi/.keys")
PROVIDER_ID = "antigravity-gemini"

# 用户明确只要这 3 个。其余上游模型写入 deletedModels，避免刷新时再冒出来。
KEEP = [
    ("gemini-3.8-flash-high", "Gemini 3.8 Flash", 65535, ["text", "image", "audio", "video"], ["text"]),
    ("gemini-3.7-flash-high", "Gemini 3.7 Flash", 65535, ["text", "image", "audio", "video"], ["text"]),
    ("gemini-pro-agent", "Gemini 3.1 Pro", 65535, ["text", "image", "audio", "video"], ["text"]),
]
TOMBSTONES = [
    "gemini-3-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-image",
    "gemini-3.6-flash-high",
    "gemini-3.1-pro-low",
]


def main() -> None:
    api_key = open(KEYS, encoding="utf-8").read().split("\n")[0].strip()
    cfg = load_cfg()
    provider = ensure_provider(cfg, PROVIDER_ID, {
        "name": "Antigravity (Gemini)",
        "kind": "anthropic",
        "apiFormat": "anthropic-messages",
        "source": "custom",
        "enabled": True,
        "options": {
            "apiKey": api_key,
            "baseURL": "http://127.0.0.1:8317",
            "apiKeyRequired": True,
        },
    })
    models = provider.setdefault("models", {})
    keep_ids = {mid for mid, *_ in KEEP}
    changed = False
    for mid in list(models):
        if mid not in keep_ids:
            del models[mid]
            changed = True
    for mid, name, cap, in_mod, out_mod in KEEP:
        model = models.setdefault(mid, {
            "name": name,
            "limit": {"context": 1048576, "output": 65536},
            "modalities": {"input": in_mod, "output": out_mod},
            "zcode": {"modified": True},
        })
        model["name"] = name
        model.setdefault("limit", {})["context"] = 1048576
        model.setdefault("limit", {})["output"] = 65536
        model["modalities"] = {"input": in_mod, "output": out_mod}
        if apply_reasoning(model, anthropic_reasoning_spec(cap=cap)):
            changed = True
    zcode = provider.setdefault("zcode", {})
    if zcode.get("deletedModels") != TOMBSTONES:
        zcode["deletedModels"] = TOMBSTONES
        changed = True
    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-antigravity")
        save_cfg(cfg)
        log("✅ Gemini provider 已更新：仅保留 3 个模型，并写入真实思考档位", important=True)
        log("   gemini-3.8-flash-high / gemini-3.7-flash-high / gemini-pro-agent", important=True)
        log("   档位 low/medium/high（默认 high）", important=True)
    else:
        log("✅ Gemini provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
