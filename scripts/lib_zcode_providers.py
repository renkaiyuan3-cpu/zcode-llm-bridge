#!/usr/bin/env python3
"""ZCode 自定义供应商的思考档位补丁。

ZCode 回写 ~/.zcode/v2/config.json 时会：
1. 删掉顶层 reasoningSpec（omitModelCarryoverKeys）
2. 把 reasoning 收成只有 variants 的 UI 标记
3. 丢掉 zcode.reasoning

所以界面上可能还有 Low/High，请求里却没有 thinking / reasoning_effort。
本模块负责把完整补丁写回去，并给 restore 脚本做幂等检查。
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import tempfile
from typing import Any

CFG = os.path.expanduser("~/.zcode/v2/config.json")

ANTHROPIC_LEVELS = [("low", 4096), ("medium", 16384), ("high", 60000)]
ANTHROPIC_XHIGH = ("xhigh", 100000)
DEFAULT_LEVEL = "high"


def now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def quiet() -> bool:
    return os.environ.get("ZCODE_RESTORE_QUIET") == "1"


def log(message: str, *, important: bool = False) -> None:
    if important or not quiet():
        print(message)


def anthropic_reasoning_spec(include_xhigh: bool = False, cap: int = 65535) -> dict[str, Any]:
    levels = list(ANTHROPIC_LEVELS)
    if include_xhigh:
        levels.append(ANTHROPIC_XHIGH)
    return {
        "defaultLevel": DEFAULT_LEVEL,
        "levels": {
            name: {
                "anthropic": {
                    "set": [{
                        "path": ["thinking"],
                        "value": {
                            "type": "enabled",
                            "budgetTokens": min(budget, cap),
                        },
                    }]
                }
            }
            for name, budget in levels
        },
    }


def openai_reasoning_spec(variants: list[str], default: str = "high") -> dict[str, Any]:
    """openai-compatible 走 reasoning_effort，不是 Anthropic thinking。"""
    alias = {"off": "none"}
    return {
        "defaultLevel": default,
        "levels": {
            name: {
                "openai-compatible": {
                    "set": [{
                        "path": ["reasoningEffort"],
                        "value": alias.get(name, name),
                    }]
                }
            }
            for name in variants
        },
    }


def ui_reasoning(spec: dict[str, Any]) -> dict[str, Any]:
    variants = list(spec.get("levels", {}))
    return {
        "enabled": bool(variants),
        "variants": variants,
        "defaultVariant": spec.get("defaultLevel", DEFAULT_LEVEL),
    }


def apply_reasoning(model: dict[str, Any], spec: dict[str, Any]) -> bool:
    """把 UI 档位 + 真实补丁写进模型。已完整则返回 False。"""
    wanted_ui = ui_reasoning(spec)
    zcode = model.setdefault("zcode", {})
    changed = (
        model.get("reasoning") != wanted_ui
        or model.get("reasoningSpec") != spec
        or zcode.get("reasoning") != spec
    )
    if not changed:
        return False
    model["reasoning"] = wanted_ui
    model["reasoningSpec"] = spec
    zcode["modified"] = True
    zcode["reasoning"] = spec
    return True


def load_cfg(path: str = CFG) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_cfg(cfg: dict[str, Any], path: str = CFG) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".zcode-config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def backup_cfg(path: str, suffix: str) -> None:
    import shutil
    shutil.copy(path, path + suffix)


def ensure_provider(cfg: dict[str, Any], provider_id: str, template: dict[str, Any]) -> dict[str, Any]:
    providers = cfg.setdefault("provider", {})
    current = providers.get(provider_id)
    if not isinstance(current, dict):
        providers[provider_id] = copy.deepcopy(template)
        providers[provider_id]["createdAt"] = now_ms()
        providers[provider_id]["updatedAt"] = now_ms()
        return providers[provider_id]
    for key in ("name", "kind", "apiFormat", "source"):
        if template.get(key) and current.get(key) != template[key]:
            current[key] = template[key]
    if template.get("options"):
        options = current.setdefault("options", {})
        options.update(template["options"])
    if template.get("headers"):
        headers = current.setdefault("headers", {})
        headers.update(template["headers"])
    if "enabled" in template:
        current["enabled"] = template["enabled"]
    current.setdefault("models", {})
    return current
