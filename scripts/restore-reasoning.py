#!/usr/bin/env python3
"""ZCode 重启回写后，把自定义供应商的思考补丁补回去。

由 launchd com.zcode.restore-reasoning 定期检查。
只有 config 真的缺补丁时才写盘，避免和 ZCode 抢文件。
"""
from pathlib import Path
import runpy
import sys
import traceback

HERE = Path(__file__).resolve().parent
SCRIPTS = [
    "apply-grok-provider.py",
    "apply-gemini-provider.py",
    "apply-opencode-go-provider.py",
    "apply-commandcode-provider.py",
    "apply-codex-provider.py",
]


def main() -> int:
    import os
    failed = 0
    quiet = "--quiet" in sys.argv or not sys.stdout.isatty()
    if quiet:
        os.environ["ZCODE_RESTORE_QUIET"] = "1"
        sys.argv = [sys.argv[0]]
    for name in SCRIPTS:
        path = HERE / name
        try:
            runpy.run_path(str(path), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (0, None):
                failed += 1
                print(f"❌ {name} exit={exc.code}", file=sys.stderr)
        except Exception:
            failed += 1
            print(f"❌ {name}", file=sys.stderr)
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
