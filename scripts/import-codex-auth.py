#!/usr/bin/env python3
"""把 ~/.codex/auth.json（嵌套结构）扁平化导入 CLIProxyAPI 的 auth-codex/。

直接复制原文件会被 CPA 静默忽略：日志里 1 auth entries、/v1/models 0 个模型。
CPA 要的是扁平字段 + type=codex。详见 docs/codex-guide.md 第 4 节。
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import sys


def b64url_json(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def flatten(src: dict) -> dict:
    tokens = src.get("tokens")
    if not isinstance(tokens, dict) or "access_token" not in tokens:
        raise SystemExit(
            "❌ auth.json 不是 Codex CLI 的嵌套结构（缺少 tokens.access_token）。\n"
            "   若 CPA 已经用 -codex-login 拿过独立凭据，不必跑本脚本。"
        )
    access = tokens["access_token"]
    id_token = tokens.get("id_token") or ""
    try:
        exp = datetime.datetime.fromtimestamp(
            b64url_json(access.split(".")[1])["exp"]
        ).astimezone()
        expired = exp.isoformat()
    except Exception:
        expired = None
    email = "unknown"
    if id_token:
        try:
            email = b64url_json(id_token.split(".")[1]).get("email") or "unknown"
        except Exception:
            pass
    out = {
        "access_token": access,
        "refresh_token": tokens.get("refresh_token"),
        "id_token": id_token,
        "account_id": tokens.get("account_id"),
        "email": email,
        "expired": expired,
        "last_refresh": src.get("last_refresh"),
        "type": "codex",
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="扁平化导入 Codex 凭据到 CLIProxyAPI")
    parser.add_argument(
        "--src",
        default=os.path.expanduser("~/.codex/auth.json"),
        help="Codex CLI / 桌面端的 auth.json（默认 ~/.codex/auth.json）",
    )
    parser.add_argument(
        "--dst-dir",
        default=os.path.expanduser("~/.cliproxyapi/auth-codex"),
        help="CPA 凭据目录（默认 ~/.cliproxyapi/auth-codex）",
    )
    args = parser.parse_args()
    if not os.path.isfile(args.src):
        raise SystemExit(
            f"❌ 找不到 {args.src}\n"
            "   Windows 也可先用 cli-proxy-api.exe -codex-login 拿独立凭据，不必导入。"
        )
    with open(args.src, encoding="utf-8") as f:
        src = json.load(f)
    out = flatten(src)
    email = out.get("email") or "unknown"
    os.makedirs(args.dst_dir, exist_ok=True)
    dst = os.path.join(args.dst_dir, f"codex-{email}.json")
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("导入完成:", dst)
    print("提醒: 这份 refresh_token 与 Codex CLI / 桌面端共用，可能互踢。")
    print("      根治：cli-proxy-api -config config-codex.yaml -codex-login")
    return 0


if __name__ == "__main__":
    sys.exit(main())
