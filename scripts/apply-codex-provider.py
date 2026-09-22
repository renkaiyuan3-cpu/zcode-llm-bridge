#!/usr/bin/env python3
"""把 Codex（ChatGPT 订阅）接入 ZCode —— 只保留 4 个 GPT 模型。幂等。

上游链路：
  ZCode ──openai-chat-completions──▶ CLIProxyAPI:8327 ──OAuth──▶ chatgpt.com/backend-api/codex

与 Antigravity Gemini 那套（config.yaml / 8317）完全隔离：
独立端口、独立凭据目录 auth-codex、独立 API Key .keys-codex。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_zcode_providers import (  # noqa: E402
    CFG,
    apply_reasoning,
    backup_cfg,
    ensure_option_specs,
    ensure_provider,
    load_cfg,
    log,
    now_ms,
    openai_reasoning_spec,
    require_cred,
    save_cfg,
)

KEYS = os.path.expanduser("~/.cliproxyapi/.keys-codex")
PROVIDER_ID = "codex-local"
BASE_URL = "http://127.0.0.1:8327/v1"

# 档位取值域取自上游实测报错信息：
#   level "ultra" not supported, valid levels: low, medium, high, xhigh, max
# 模型目录里 astra/sol/terra 还标了 ultra，但 CPA 会直接拒掉，所以不能抄。
# 速度档（service_tier: priority/ultrafast）实测无效——即使绕过代理直接打
# chatgpt.com 后端，回显也恒为 "default"，属 Plus 订阅的账号级限制。
# 因此这里不暴露速度档：加了就是一条永远不生效的假档位。
LEVELS = ["low", "medium", "high", "xhigh", "max"]
DEFAULT_LEVEL = "high"

# 上下文窗口：1,000,000。
# 推导链（三处独立证据互相印证）：
#   1. 官方模型文档：GPT-5.6 全系支持 1,050,000 token 上下文、128K 最大输出。
#   2. 模型目录里 context_window=272000 只是「默认值」，另有 max_context_window=872000
#      ——872000 恰好 = 1000000 − 128000（输出预留），说明 1M 是官方开放的可选总窗口。
#   3. OpenAI Codex 工程师 Tibo 给出的开启方式就是 model_context_window = 1000000。
# ZCode 的 limit.context 记的是「总窗口」，output 单列（与 Command Code 的
# gpt-5.6-luna 写 1050000 是同一约定），所以这里填 1M 而不是 872K。
#
# ⚠️ 成本陷阱：单次请求输入超过 272K 时，上游按 2x 输入 / 1.5x 输出计价，
#    且乘的是**整个请求**而不是超出部分。开 1M 会显著加快订阅额度消耗。
CTX = 1000000
OUT = 128000
KEEP = [
    ("gpt-6-astra", "GPT-6-Astra", CTX, OUT),
    ("gpt-5.6-sol", "GPT-5.6-Sol", CTX, OUT),
    ("gpt-5.6-terra", "GPT-5.6-Terra", CTX, OUT),
    ("gpt-5.6-luna", "GPT-5.6-Luna", CTX, OUT),
]
# 上游 CPA 还会报这些，全部写进 deletedModels，避免 ZCode 刷新模型时冒出来。
TOMBSTONES = [
    "gpt-5.5",
    "codex-auto-review",
    "gpt-image-1.5",
    "gpt-image-2",
    "gpt-image-2.5",
    "gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst",
]
INPUT_MODALITIES = ["text", "image"]


def main() -> None:
    require_cred(
        KEYS,
        "Codex",
        "先启动 Codex 版 CLIProxyAPI 并把本地 API Key 写入 ~/.cliproxyapi/.keys-codex。",
    )
    api_key = open(KEYS, encoding="utf-8").read().split("\n")[0].strip()

    cfg = load_cfg()
    provider, changed = ensure_provider(cfg, PROVIDER_ID, {
        "name": "Codex",
        "kind": "openai-compatible",
        "apiFormat": "openai-chat-completions",
        "source": "custom",
        "enabled": True,
        "options": {
            "apiKey": api_key,
            "baseURL": BASE_URL,
            "apiKeyRequired": True,
        },
    })
    models = provider.setdefault("models", {})
    keep_ids = {mid for mid, *_ in KEEP}
    stale = [mid for mid in list(models) if mid not in keep_ids]
    for mid in stale:
        del models[mid]
    changed = changed or bool(stale)

    spec = openai_reasoning_spec(LEVELS, DEFAULT_LEVEL)
    for mid, name, ctx, out in KEEP:
        model = models.setdefault(mid, {
            "name": name,
            "limit": {"context": ctx, "output": out},
            "modalities": {"input": INPUT_MODALITIES, "output": ["text"]},
            "zcode": {"modified": True},
        })
        if model.get("name") != name:
            model["name"] = name
            changed = True
        if model.setdefault("limit", {}).get("context") != ctx:
            model["limit"]["context"] = ctx
            changed = True
        if model["limit"].get("output") != out:
            model["limit"]["output"] = out
            changed = True
        want_mod = {"input": INPUT_MODALITIES, "output": ["text"]}
        if model.get("modalities") != want_mod:
            model["modalities"] = want_mod
            changed = True
        if apply_reasoning(model, spec):
            changed = True

    zcode = provider.setdefault("zcode", {})
    if zcode.get("deletedModels") != TOMBSTONES:
        zcode["deletedModels"] = TOMBSTONES
        changed = True

    if ensure_option_specs(PROVIDER_ID, {mid: list(LEVELS) for mid, *_ in KEEP}):
        changed = True
        log("✅ provider_config.json 档位(optionSpecs)已写入 Codex 模型", important=True)

    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-codex")
        save_cfg(cfg)
        log("✅ Codex provider 已更新：4 个模型 + 真实思考档位", important=True)
        log("   gpt-6-astra / gpt-5.6-sol / gpt-5.6-terra / gpt-5.6-luna", important=True)
        log("   档位 low/medium/high/xhigh/max（默认 high），走 reasoning_effort", important=True)
    else:
        log("✅ Codex provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
