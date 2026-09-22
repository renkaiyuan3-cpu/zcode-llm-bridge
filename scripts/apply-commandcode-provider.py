#!/usr/bin/env python3
"""把 Command Code（$10 订阅）接到 ZCode，只暴露 DeepSeek V4.1 Flash 与 GPT-5.6 Luna。

实测要点（2026-09-16）：
1. 上游是 OpenAI Compatible，思考参数用 `reasoning_effort`，两个模型都真实生效。
2. 上游只接受 low|medium|high|xhigh|max，传 none 会 HTTP 400 —— 所以档位里绝不能有 off。
   这正是本项目 README 2.1 说的「UI 假档位」的反面：档位必须和上游取值域对齐，
   否则用户选中那一档就是一条必挂的请求。
3. 两个模型都不支持 PDF 输入（`file` 内容类型返回 400），只支持 text + image。
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
    quiet,
    resolve_picker_provider_id,
    save_cfg,
)

# 供应商 ID 是任意字符串。默认用友好 ID；如果你的 ZCode 里已有一个 UUID 形态的
# 既有 Command Code 条目，设置环境变量 COMMANDCODE_PROVIDER_ID 沿用旧 ID，
# 避免历史会话的 modelRef 失效。
PROVIDER_ID = os.environ.get("COMMANDCODE_PROVIDER_ID", "commandcode-local")
API_KEY_FILE = os.path.expanduser("~/.commandcode/api_key")
BASE_URL = "https://api.commandcode.ai/provider/v1"

# 上游取值域，off/none 不在其中。
VARIANTS = ["low", "medium", "high", "xhigh", "max"]

MODELS = {
    "deepseek/deepseek-v4.1-flash": {
        "name": "DeepSeek V4.1 Flash",
        "context": 1000000,
        "output": 128000,
    },
    "gpt-5.6-luna": {
        "name": "GPT-5.6 Luna",
        "context": 1050000,
        "output": 128000,
    },
}

# /provider/v1/models 里除上面两个之外的全部条目，防止刷新时 69 个模型涌进 UI。
DELETED_MODELS = [
    "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5-1", "claude-fable-5",
    "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-haiku-4-5-20251001",
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.4-mini",
    "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-vision-exp", "deepseek/deepseek-v4-flash-fast",
    "moonshotai/Kimi-K3", "moonshotai/Kimi-K2.7-Code", "moonshotai/Kimi-K2.7-Code-Highspeed",
    "moonshotai/Kimi-K2.6", "moonshotai/Kimi-K2.5",
    "z-ai/glm-5.3-flash", "zai-org/GLM-5.3", "zai-org/GLM-5.2", "zai-org/GLM-5.2-Fast",
    "zai-org/GLM-5.1", "zai-org/GLM-5",
    "MiniMaxAI/MiniMax-M3", "MiniMaxAI/MiniMax-M2.7", "MiniMaxAI/MiniMax-M2.5",
    "xiaomi/mimo-v2.5-pro", "xiaomi/mimo-v2.5",
    "Qwen/Qwen3.8-Max-0902", "Qwen/Qwen3.8-Max", "Qwen/Qwen3.8-27B", "Qwen/Qwen3.8-Flash",
    "Qwen/Qwen3.7-Max", "Qwen/Qwen3.7-Plus", "Qwen/Qwen3.7-Flash",
    "Qwen/Qwen3.6-Max-Preview", "Qwen/Qwen3.6-Plus",
    "meituan/LongCat-2.0:free", "stepfun/Step-3.7-Flash", "stepfun/Step-3.5-Flash",
    "tencent/hy3-paid", "tencent/hy4-preview",
    "google/gemini-3.8-flash", "google/gemini-3.7-flash", "google/gemini-3.6-flash",
    "google/gemini-3.5-flash", "google/gemini-3.5-flash-lite", "google/gemini-3.1-flash-lite",
    "sakana/fugu-ultra", "nvidia/nemotron-3-ultra-550b-a55b",
    "thinkingmachines/inkling", "thinkingmachines/inkling-small",
    "poolside/laguna-s-2.1-free", "inclusionai/ling-3.0-flash-sante:free",
    "meta/muse-spark-1.1", "meta/muse-spark-1.2", "meta/muse-spark-1.2-contributor",
    "meta/muse-spark-1.3", "meta/muse-spark-1.3-contributor",
    "xai/grok-4.5", "xai/grok-4.6",
]


def load_api_key() -> str:
    env = os.environ.get("COMMANDCODE_API_KEY", "").strip()
    if env:
        return env
    if os.path.isfile(API_KEY_FILE):
        return open(API_KEY_FILE, encoding="utf-8").read().strip()
    if quiet():
        log("跳过 Command Code：未找到 ~/.commandcode/api_key")
        raise SystemExit(0)
    raise SystemExit(
        "缺少 Command Code API Key。请写入 ~/.commandcode/api_key，"
        "或设置环境变量 COMMANDCODE_API_KEY 后再跑本脚本。"
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
        raise SystemExit("缺少 Command Code API Key")
    persist_api_key(api_key)
    cfg = load_cfg()
    provider, changed = ensure_provider(cfg, PROVIDER_ID, {
        "name": "Command Code",
        "kind": "openai-compatible",
        "apiFormat": "openai-chat-completions",
        "source": "custom",
        "enabled": True,
        "options": {
            "apiKey": api_key,
            "baseURL": BASE_URL,
            "apiKeyRequired": True,
        },
        "headers": {"User-Agent": "ZCode"},
    })

    spec = openai_reasoning_spec(VARIANTS, default="high")
    models = provider.setdefault("models", {})
    for mid in list(models):
        if mid not in MODELS:
            del models[mid]

    changed = False
    for mid, meta in MODELS.items():
        model = models.setdefault(mid, {
            "zcode": {"modified": True},
        })
        model["name"] = meta["name"]
        model.setdefault("limit", {})["context"] = meta["context"]
        model.setdefault("limit", {})["output"] = meta["output"]
        # 上游不支持 PDF 输入，别在 UI 里勾上。
        model["modalities"] = {"input": ["text", "image"], "output": ["text"]}
        model.setdefault("zcode", {})["modalitiesConfigured"] = True
        # 思考档位必须和上游取值域一致，否则选中即 400。
        changed = apply_reasoning(model, spec) or changed

    zcode = provider.setdefault("zcode", {})
    if zcode.get("deletedModels") != DELETED_MODELS:
        zcode["deletedModels"] = DELETED_MODELS
        changed = True

    # 选择器里的 Command Code 可能是 UUID 形态旧条目，optionSpecs 要写对 ID
    picker_id = resolve_picker_provider_id("Command Code", PROVIDER_ID)
    if ensure_option_specs(picker_id, {mid: list(VARIANTS) for mid in MODELS}):
        changed = True
        log(f"✅ provider_config.json 档位(optionSpecs)已写入 Command Code 模型（{picker_id}）",
            important=True)

    if changed:
        provider["updatedAt"] = now_ms()
        backup_cfg(CFG, ".bak-commandcode")
        save_cfg(cfg)
        log("✅ Command Code 已接入：DeepSeek V4.1 Flash + GPT-5.6 Luna", important=True)
        log("   endpoint: %s/chat/completions" % BASE_URL, important=True)
        log("   档位:     low/medium/high/xhigh/max（默认 high，对应 reasoning_effort）",
            important=True)
        log("   注意:     上游不接受 off/none，选中即 HTTP 400", important=True)
    else:
        log("✅ Command Code provider 已是最新，无需改写")


if __name__ == "__main__":
    main()
