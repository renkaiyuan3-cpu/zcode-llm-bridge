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
PROVIDER_CFG = os.path.expanduser("~/.zcode/v2/provider_config.json")

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
    default = spec.get("defaultLevel", DEFAULT_LEVEL)
    return {
        "enabled": bool(variants),
        # App(旧 opencode schema)读 variants/defaultVariant
        "variants": variants,
        "defaultVariant": default,
        # CLI(zcode.cjs xqa schema)读 levels/defaultLevel；
        # 两个 schema 都不是 strict，多余键会被剥离/透传，混写安全
        "levels": list(variants),
        "defaultLevel": default,
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


def resolve_picker_provider_id(
    name: str, fallback: str, path: str = PROVIDER_CFG
) -> str:
    """按 providerName 在 provider_config.json 里找选择器实际用的 providerId。

    早期手动添加的供应商（如 Command Code）在选择器里是 UUID 形态，
    与 config.json 的友好 ID 不同；写 optionSpecs 必须用选择器那个。
    """
    try:
        with open(path, encoding="utf-8") as f:
            pc = json.load(f)
    except (OSError, ValueError):
        return fallback
    rules = pc.get("config", {}).get("providerConfigRules", {}).get("providerRules", [])
    for rule in rules:
        if isinstance(rule, dict) and rule.get("providerName") == name and rule.get("providerId"):
            return str(rule["providerId"])
    return fallback


def ensure_option_specs(
    provider_id: str,
    model_levels: dict[str, list[str]],
    path: str = PROVIDER_CFG,
) -> bool:
    """把 optionSpecs.reasoningLevel.values 写进 provider_config.json 的 modelConfigRules。

    ZCode 3.14 起编辑器/选择器的档位来自模型注册表（optionSpecs），
    与 config.json 的 variants 互补；两处都写才能稳定显示档位下拉。
    model_levels: {model_id: [level, ...]}。返回是否有改动。
    """
    if not os.path.isfile(path) or not model_levels:
        return False
    with open(path, encoding="utf-8") as f:
        pc = json.load(f)
    entries = pc.get("config", {}).get("modelConfigRules", {}).get("providerModelRules")
    if not isinstance(entries, list):
        return False
    index = {
        rule.get("modelId"): i
        for i, rule in enumerate(entries)
        if isinstance(rule, dict) and rule.get("providerId") == provider_id
    }
    changed = False
    for mid, levels in model_levels.items():
        wanted = {"values": list(levels)}
        i = index.get(mid)
        if i is None:
            entries.append({
                "modelId": mid,
                "config": {"optionSpecs": {"reasoningLevel": wanted}},
                "providerId": provider_id,
            })
            changed = True
            continue
        rule = entries[i]
        config = rule.setdefault("config", {})
        specs = config.setdefault("optionSpecs", {})
        if specs.get("reasoningLevel") != wanted:
            specs["reasoningLevel"] = wanted
            changed = True
    if changed:
        backup_cfg(path, ".bak-optionspecs")
        save_cfg(pc, path)
    return changed


def require_cred(path: str, label: str, hint: str) -> None:
    """凭据不存在时：交互运行直接失败，自愈任务（quiet）则跳过该通道。"""
    if os.path.isfile(path):
        return
    if quiet():
        log(f"跳过 {label}：未找到 {path}")
        raise SystemExit(0)
    raise SystemExit(f"❌ 找不到 {path}\n   {hint}")


def load_cfg(path: str = CFG) -> dict[str, Any]:
    if not os.path.isfile(path):
        raise SystemExit(
            f"❌ 找不到 ZCode 配置 {path}\n"
            "   请先安装并至少成功启动一次 ZCode 客户端（https://z.ai），\n"
            "   它会在首次启动时生成该文件。\n"
            "   Windows 一般为 %USERPROFILE%\\.zcode\\v2\\config.json"
        )
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


def ensure_provider(
    cfg: dict[str, Any], provider_id: str, template: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """写入供应商模板。返回 (provider, changed)。

    原先只在思考档位变化时存盘，API Key 轮换后会悄悄丢更新。
    """
    providers = cfg.setdefault("provider", {})
    current = providers.get(provider_id)
    changed = False
    if not isinstance(current, dict):
        providers[provider_id] = copy.deepcopy(template)
        providers[provider_id]["createdAt"] = now_ms()
        providers[provider_id]["updatedAt"] = now_ms()
        return providers[provider_id], True
    for key in ("name", "kind", "apiFormat", "source"):
        if template.get(key) and current.get(key) != template[key]:
            current[key] = template[key]
            changed = True
    if template.get("options"):
        options = current.setdefault("options", {})
        for key, value in template["options"].items():
            if options.get(key) != value:
                options[key] = value
                changed = True
    if template.get("headers"):
        headers = current.setdefault("headers", {})
        for key, value in template["headers"].items():
            if headers.get(key) != value:
                headers[key] = value
                changed = True
    if "enabled" in template and current.get("enabled") != template["enabled"]:
        current["enabled"] = template["enabled"]
        changed = True
    current.setdefault("models", {})
    return current, changed
