#!/usr/bin/env python3
"""跨平台入口：体检、安装自愈任务、拉起本地代理、下载上游二进制。

macOS 仍走 launchd；Windows 走计划任务；Linux 走 systemd --user（beta）。
陌生人请先跑：

    python3 scripts/bridge.py doctor          # macOS / Linux
    py -3 scripts\\bridge.py doctor           # Windows
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
RUNTIME = HOME / ".zcode-proxy"
ZCODE_CFG = HOME / ".zcode" / "v2" / "config.json"
ZCODE_LOGS = HOME / ".zcode" / "v2" / "logs"

TASK_RESTORE = "ZCodeLLMBridge.RestoreReasoning"
TASK_GROK = "ZCodeLLMBridge.GrokProxy"
TASK_GEMINI = "ZCodeLLMBridge.GeminiProxy"
TASK_CODEX = "ZCodeLLMBridge.CodexProxy"

PORTS = {
    "grok": 8080,
    "gemini": 8317,
    "codex": 8327,
}

CPA_REPO = "router-for-me/CLIProxyAPI"
GROK_REPO = "GreyGunG/grokbuild-proxy"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def python_exe() -> str:
    return sys.executable


def bin_candidates(directory: Path, names: Iterable[str]) -> Path | None:
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    return None


def grok_bin() -> Path | None:
    return bin_candidates(
        HOME / ".grokbuild-proxy",
        ("grokbuild-proxy.exe", "grokbuild-proxy"),
    )


def cpa_bin() -> Path | None:
    return bin_candidates(
        HOME / ".cliproxyapi",
        ("cli-proxy-api.exe", "cli-proxy-api", "CLIProxyAPI.exe"),
    )


def listening(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 3.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "zcode-llm-bridge"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b""
    except OSError:
        return 0, b""


def first_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return text[0].strip() if text else None


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    print(f"  ❌ {msg}")


def info(msg: str) -> None:
    print(f"  •  {msg}")


def copy_runtime() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not is_windows():
        os.chmod(RUNTIME, 0o700)
    ZCODE_LOGS.mkdir(parents=True, exist_ok=True)
    src_dir = REPO / "scripts"
    for src in src_dir.glob("*.py"):
        shutil.copy2(src, RUNTIME / src.name)
    print(f"✅ 已同步脚本到 {RUNTIME}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

def macos_install(target: str) -> int:
    installer = REPO / "launchd" / "install-launchd.sh"
    if not installer.is_file():
        print(f"❌ 找不到 {installer}")
        return 1
    proc = run(["bash", str(installer), target])
    return proc.returncode


def macos_kickstart(label: str) -> None:
    uid = os.getuid()
    run(["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"], check=False)


def macos_task_loaded(label: str) -> bool:
    proc = run(["launchctl", "list", label], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Windows Scheduled Tasks
# ---------------------------------------------------------------------------

def powershell(script: str) -> subprocess.CompletedProcess:
    encoded = script
    return run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", encoded,
        ],
        capture_output=True,
        text=True,
    )


def win_task_exists(name: str) -> bool:
    proc = run(
        ["schtasks", "/Query", "/TN", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def win_register_logon_task(
    name: str,
    execute: str,
    arguments: str,
    workdir: str,
    *,
    repeat_minutes: int | None = None,
    start_now: bool = True,
) -> None:
    """登录触发 + 失败重启；可选每 N 分钟重复。ExecutionTimeLimit 必须为 0，否则 72h 后被杀。"""
    workdir_ps = workdir.replace("'", "''")
    execute_ps = execute.replace("'", "''")
    arguments_ps = arguments.replace("'", "''")
    extra_repeat = ""
    if repeat_minutes:
        extra_repeat = f"""
$task = Get-ScheduledTask -TaskName '{name}'
$task.Triggers[0].Repetition.Interval = 'PT{repeat_minutes}M'
$task.Triggers[0].Repetition.Duration = 'P9999D'
$task.Triggers[0].Repetition.StopAtDurationEnd = $false
Set-ScheduledTask -InputObject $task | Out-Null
"""
    start = f"Start-ScheduledTask -TaskName '{name}'" if start_now else ""
    script = f"""
$action = New-ScheduledTaskAction -Execute '{execute_ps}' -Argument '{arguments_ps}' -WorkingDirectory '{workdir_ps}'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName '{name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
{extra_repeat}
{start}
"""
    proc = powershell(script)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"❌ 注册计划任务 {name} 失败：{err}")
    print(f"✅ 已安装计划任务 {name}")


def win_unregister(name: str) -> None:
    run(["schtasks", "/Delete", "/TN", name, "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def win_start(name: str) -> None:
    run(["schtasks", "/Run", "/TN", name], check=False)


def win_end(name: str) -> None:
    run(["schtasks", "/End", "/TN", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Linux systemd --user
# ---------------------------------------------------------------------------

def linux_write_unit(name: str, exec_start: str, workdir: str, *, timer_sec: int | None = None) -> None:
    unit_dir = HOME / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = f"""[Unit]
Description={name}
After=network.target

[Service]
Type=simple
WorkingDirectory={workdir}
ExecStart={exec_start}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
"""
    (unit_dir / f"{name}.service").write_text(service, encoding="utf-8")
    if timer_sec:
        # 自愈任务用 oneshot + timer，不用 Restart=always 的常驻进程。
        service = f"""[Unit]
Description={name}

[Service]
Type=oneshot
WorkingDirectory={workdir}
ExecStart={exec_start}
"""
        (unit_dir / f"{name}.service").write_text(service, encoding="utf-8")
        timer = f"""[Unit]
Description={name} timer

[Timer]
OnBootSec=30
OnUnitActiveSec={timer_sec}

[Install]
WantedBy=timers.target
"""
        (unit_dir / f"{name}.timer").write_text(timer, encoding="utf-8")
        run(["systemctl", "--user", "daemon-reload"], check=False)
        run(["systemctl", "--user", "enable", "--now", f"{name}.timer"], check=False)
    else:
        run(["systemctl", "--user", "daemon-reload"], check=False)
        run(["systemctl", "--user", "enable", "--now", f"{name}.service"], check=False)
    print(f"✅ 已安装 systemd 用户单元 {name}")


# ---------------------------------------------------------------------------
# install targets
# ---------------------------------------------------------------------------

def quote_arg(value: str) -> str:
    if is_windows():
        return f'"{value}"'
    return value


def install_restore() -> int:
    copy_runtime()
    py = python_exe()
    script = str(RUNTIME / "restore-reasoning.py")
    if is_macos():
        return macos_install("restore")
    if is_windows():
        win_register_logon_task(
            TASK_RESTORE,
            py,
            f'{quote_arg(script)} --quiet',
            str(RUNTIME),
            repeat_minutes=1,
        )
        return 0
    linux_write_unit(
        "zcode-restore-reasoning",
        f"{py} {script} --quiet",
        str(RUNTIME),
        timer_sec=60,
    )
    return 0


def install_grok() -> int:
    binary = grok_bin()
    if binary is None:
        print("❌ 未找到 ~/.grokbuild-proxy/grokbuild-proxy，先跑 `bridge.py fetch` 或按文档手动安装。")
        return 1
    cfg = HOME / ".grokbuild-proxy" / "config.yaml"
    if not cfg.is_file():
        print("❌ 未找到 ~/.grokbuild-proxy/config.yaml，请先复制 templates/grokbuild-proxy.example.yaml")
        return 1
    if is_macos():
        return macos_install("grok")
    if is_windows():
        win_register_logon_task(
            TASK_GROK,
            str(binary),
            f'-config {quote_arg(str(cfg))}',
            str(HOME / ".grokbuild-proxy"),
        )
        return 0
    linux_write_unit(
        "zcode-grokbuild-proxy",
        f"{binary} -config {cfg}",
        str(HOME / ".grokbuild-proxy"),
    )
    return 0


def install_gemini() -> int:
    binary = cpa_bin()
    if binary is None:
        print("❌ 未找到 ~/.cliproxyapi/cli-proxy-api，先跑 `bridge.py fetch` 或按文档手动安装。")
        return 1
    cfg = HOME / ".cliproxyapi" / "config.yaml"
    if not cfg.is_file():
        print("❌ 未找到 ~/.cliproxyapi/config.yaml，请先复制 templates/cliproxyapi-gemini.example.yaml")
        return 1
    if is_macos():
        return macos_install("gemini")
    if is_windows():
        win_register_logon_task(
            TASK_GEMINI,
            str(binary),
            f'-config {quote_arg(str(cfg))}',
            str(HOME / ".cliproxyapi"),
        )
        return 0
    linux_write_unit(
        "zcode-cliproxyapi-gemini",
        f"{binary} -config {cfg}",
        str(HOME / ".cliproxyapi"),
    )
    return 0


def install_codex() -> int:
    binary = cpa_bin()
    if binary is None:
        print("❌ 未找到 ~/.cliproxyapi/cli-proxy-api，先跑 `bridge.py fetch` 或按文档手动安装。")
        return 1
    cfg = HOME / ".cliproxyapi" / "config-codex.yaml"
    if not cfg.is_file():
        print("❌ 未找到 ~/.cliproxyapi/config-codex.yaml，请先复制 templates/cliproxyapi-codex.example.yaml")
        return 1
    if is_macos():
        return macos_install("codex")
    if is_windows():
        win_register_logon_task(
            TASK_CODEX,
            str(binary),
            f'-config {quote_arg(str(cfg))}',
            str(HOME / ".cliproxyapi"),
        )
        return 0
    linux_write_unit(
        "zcode-cliproxyapi-codex",
        f"{binary} -config {cfg}",
        str(HOME / ".cliproxyapi"),
    )
    return 0


def cmd_install(target: str) -> int:
    mapping = {
        "restore": install_restore,
        "grok": install_grok,
        "gemini": install_gemini,
        "codex": install_codex,
    }
    if target == "all":
        rc = 0
        for name in ("grok", "gemini", "codex", "restore"):
            print(f"--- install {name} ---")
            result = mapping[name]()
            if result != 0:
                print(f"（跳过 {name}）")
                rc = result if name == "restore" else rc
        return rc
    if target not in mapping:
        print("用法: bridge.py install {restore|grok|gemini|codex|all}")
        return 1
    return mapping[target]()


def cmd_uninstall() -> int:
    if is_macos():
        uid = os.getuid()
        for label in (
            "com.zcode.restore-reasoning",
            "com.grokbuild.proxy",
            "com.cliproxyapi",
            "com.cliproxyapi.codex",
        ):
            run(["launchctl", "bootout", f"gui/{uid}/{label}"], check=False)
            plist = HOME / "Library" / "LaunchAgents" / f"{label}.plist"
            if plist.exists():
                plist.unlink()
            print(f"✅ 已卸载 {label}")
        return 0
    if is_windows():
        for name in (TASK_RESTORE, TASK_GROK, TASK_GEMINI, TASK_CODEX):
            win_end(name)
            win_unregister(name)
            print(f"✅ 已卸载 {name}")
        return 0
    for name in (
        "zcode-restore-reasoning",
        "zcode-grokbuild-proxy",
        "zcode-cliproxyapi-gemini",
        "zcode-cliproxyapi-codex",
    ):
        run(["systemctl", "--user", "disable", "--now", f"{name}.timer"], check=False)
        run(["systemctl", "--user", "disable", "--now", f"{name}.service"], check=False)
        print(f"✅ 已卸载 {name}")
    return 0


# ---------------------------------------------------------------------------
# status / restart / logs
# ---------------------------------------------------------------------------

def scheduler_status() -> None:
    print("--- 调度器 ---")
    if is_macos():
        for label in (
            "com.grokbuild.proxy",
            "com.cliproxyapi",
            "com.cliproxyapi.codex",
            "com.zcode.restore-reasoning",
        ):
            (ok if macos_task_loaded(label) else bad)(label)
        return
    if is_windows():
        for name in (TASK_GROK, TASK_GEMINI, TASK_CODEX, TASK_RESTORE):
            (ok if win_task_exists(name) else bad)(name)
        return
    info("Linux：用 systemctl --user status zcode-* 查看")


def check_models(port: int, label: str, keys: Path) -> None:
    key = first_line(keys)
    if not key:
        bad(f"{label} ({port} /v1/models): 未找到 {keys}")
        return
    code, body = http_get(
        f"http://127.0.0.1:{port}/v1/models",
        headers={"Authorization": f"Bearer {key}", "User-Agent": "zcode-llm-bridge"},
    )
    if code == 200:
        try:
            count = len(json.loads(body.decode("utf-8")).get("data", []))
        except Exception:
            count = "?"
        ok(f"{label} ({port} /v1/models): HTTP 200 ({count} 个模型)")
        return
    bad(f"{label} ({port} /v1/models): HTTP {code or '无法访问'}")


def cmd_status() -> int:
    print("==================== [服务运行状态] ====================")
    print(f"系统: {platform.system()} {platform.machine()}  Python: {platform.python_version()}")
    scheduler_status()
    print("--- 端口 ---")
    for name, port in PORTS.items():
        (ok if listening(port) else bad)(f"{port} ({name})")
    print("--- HTTP ---")
    code, body = http_get("http://127.0.0.1:8080/readyz")
    if code == 200:
        ok(f"Grok /readyz: {body.decode('utf-8', 'replace').strip() or '200'}")
    else:
        bad("Grok /readyz: 无法访问")
    check_models(8317, "CLIProxyAPI Gemini", HOME / ".cliproxyapi" / ".keys")
    check_models(8327, "CLIProxyAPI Codex", HOME / ".cliproxyapi" / ".keys-codex")
    print("========================================================")
    return 0


def cmd_restart(target: str) -> int:
    if is_macos():
        mapping = {
            "grok": "com.grokbuild.proxy",
            "gemini": "com.cliproxyapi",
            "codex": "com.cliproxyapi.codex",
            "restore": "com.zcode.restore-reasoning",
        }
        labels = list(mapping.values()) if target == "all" else [mapping[target]]
        for label in labels:
            macos_kickstart(label)
            print(f"已发送重启指令 {label}")
        return 0
    if is_windows():
        mapping = {
            "grok": TASK_GROK,
            "gemini": TASK_GEMINI,
            "codex": TASK_CODEX,
            "restore": TASK_RESTORE,
        }
        names = list(mapping.values()) if target == "all" else [mapping[target]]
        for name in names:
            win_end(name)
            win_start(name)
            print(f"已发送重启指令 {name}")
        return 0
    print("Linux：systemctl --user restart zcode-grokbuild-proxy.service 等")
    return 0


def tail_file(path: Path, n: int = 15) -> None:
    print(f"=== {path} ===")
    if not path.is_file():
        print("无日志")
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-n:]) or "（空）")


def cmd_logs() -> int:
    tail_file(HOME / ".grokbuild-proxy" / "proxy.log")
    print()
    tail_file(HOME / ".cliproxyapi" / "server.log")
    print()
    tail_file(HOME / ".cliproxyapi" / "codex-server.log")
    print()
    tail_file(ZCODE_LOGS / "restore-reasoning.err.log", 8)
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor() -> int:
    print("==================== [安装体检] ====================")
    print(f"系统: {platform.system()} {platform.release()} {platform.machine()}")
    py_ok = sys.version_info >= (3, 9)
    (ok if py_ok else bad)(f"Python {platform.python_version()}（需要 3.9+）  {python_exe()}")
    if ZCODE_CFG.is_file():
        ok(f"ZCode 配置存在: {ZCODE_CFG}")
    else:
        bad(f"还没有 {ZCODE_CFG}")
        info("请先从 https://z.ai 安装 ZCode 并成功启动一次，再跑注入脚本。")
    print("--- 直连 API 通道（无需本地代理，Mac/Windows 相同）---")
    (ok if (HOME / ".commandcode" / "api_key").is_file() else info)(
        "~/.commandcode/api_key " + ("已就绪" if (HOME / ".commandcode" / "api_key").is_file() else "未配置（可选）")
    )
    (ok if (HOME / ".opencode-go" / "api_key").is_file() else info)(
        "~/.opencode-go/api_key " + ("已就绪" if (HOME / ".opencode-go" / "api_key").is_file() else "未配置（可选）")
    )
    print("--- 本地代理二进制 ---")
    gb = grok_bin()
    (ok if gb else info)(f"grokbuild-proxy: {gb or '未安装（可选，bridge.py fetch 可下载）'}")
    cpa = cpa_bin()
    (ok if cpa else info)(f"cli-proxy-api: {cpa or '未安装（可选，bridge.py fetch 可下载）'}")
    meta = HOME / ".grokbuild-proxy" / "data" / "meta.json"
    (ok if meta.is_file() else info)("Grok 设备码授权 " + ("已完成" if meta.is_file() else "未完成"))
    (ok if (HOME / ".cliproxyapi" / ".keys").is_file() else info)("Gemini .keys " + ("已就绪" if (HOME / ".cliproxyapi" / ".keys").is_file() else "未配置"))
    (ok if (HOME / ".cliproxyapi" / ".keys-codex").is_file() else info)(
        "Codex .keys-codex " + ("已就绪" if (HOME / ".cliproxyapi" / ".keys-codex").is_file() else "未配置")
    )
    print("--- 自愈运行时 ---")
    restore = RUNTIME / "restore-reasoning.py"
    (ok if restore.is_file() else info)(
        f"{RUNTIME} " + ("已安装" if restore.is_file() else "尚未 install restore")
    )
    scheduler_status()
    print("--- 端口（没接的通道显示未监听是正常的）---")
    for name, port in PORTS.items():
        (ok if listening(port) else info)(f"{port} {name} " + ("在听" if listening(port) else "未监听"))
    print()
    if not ZCODE_CFG.is_file():
        print("下一步：启动 ZCode → 再跑 python3 scripts/bridge.py doctor")
    elif not (HOME / ".commandcode" / "api_key").is_file() and not meta.is_file() and not (HOME / ".cliproxyapi" / ".keys").is_file():
        print("下一步（最快）：把 API Key 写入 ~/.commandcode/api_key 后执行")
        print("  python3 scripts/apply-commandcode-provider.py")
        print("  python3 scripts/bridge.py install restore")
        print("或看 docs/windows-guide.md / README 快速开始。")
    else:
        print("已有通道凭据。注入：python3 scripts/apply-*-provider.py")
        print("自愈：python3 scripts/bridge.py install restore")
        print("然后重启 ZCode 客户端。")
    print("========================================================")
    return 0 if py_ok else 1


# ---------------------------------------------------------------------------
# fetch upstream binaries
# ---------------------------------------------------------------------------

def github_latest_assets(repo: str) -> tuple[str, list[dict]]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "zcode-llm-bridge",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("tag_name") or "unknown", data.get("assets") or []


def current_asset_token() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "Darwin":
        return ("darwin_aarch64", "Darwin_arm64") if arm else ("darwin_amd64", "Darwin_x86_64")
    if system == "Windows":
        return ("windows_aarch64", "Windows_arm64") if arm else ("windows_amd64", "Windows_x86_64")
    return ("linux_aarch64", "Linux_arm64") if arm else ("linux_amd64", "Linux_x86_64")


def pick_asset(assets: list[dict], tokens: tuple[str, str], archive_exts: tuple[str, ...]) -> dict | None:
    lowered = []
    for asset in assets:
        name = asset.get("name") or ""
        if name.endswith(archive_exts) and not name.endswith(".sbom.json"):
            lowered.append(asset)
    for token in tokens:
        token_l = token.lower()
        for asset in lowered:
            if token_l in (asset.get("name") or "").lower():
                return asset
    return None


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "zcode-llm-bridge"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def extract_binary(archive: Path, dest_dir: Path, wanted: tuple[str, ...]) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if archive.suffix == ".zip" or archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp_path)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(tmp_path)
        found = None
        for root, _dirs, files in os.walk(tmp_path):
            for name in files:
                if name in wanted or name.lower() in {w.lower() for w in wanted}:
                    found = Path(root) / name
                    break
            if found:
                break
        if found is None:
            raise SystemExit(f"❌ 压缩包里没有找到 {wanted}: {archive.name}")
        target_name = wanted[0]
        target = dest_dir / target_name
        shutil.copy2(found, target)
        if not is_windows():
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target


def fetch_one(repo: str, dest_dir: Path, wanted: tuple[str, ...], label: str) -> Path:
    print(f"下载 {label}（{repo} latest）...")
    tag, assets = github_latest_assets(repo)
    tokens = current_asset_token()
    asset = pick_asset(assets, tokens, (".zip", ".tar.gz", ".tgz"))
    if asset is None:
        names = ", ".join(a.get("name") or "" for a in assets)
        raise SystemExit(f"❌ {repo} {tag} 没有匹配 {tokens} 的包。现有: {names}")
    url = asset.get("browser_download_url")
    print(f"  {asset.get('name')} ({tag})")
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / asset["name"]
    download(url, archive)
    binary = extract_binary(archive, dest_dir, wanted)
    try:
        archive.unlink()
    except OSError:
        pass
    print(f"✅ {label} -> {binary}")
    return binary


def cmd_fetch() -> int:
    cpa_wanted = ("cli-proxy-api.exe", "cli-proxy-api") if is_windows() else ("cli-proxy-api",)
    grok_wanted = ("grokbuild-proxy.exe", "grokbuild-proxy") if is_windows() else ("grokbuild-proxy",)
    fetch_one(CPA_REPO, HOME / ".cliproxyapi", cpa_wanted, "CLIProxyAPI")
    fetch_one(GROK_REPO, HOME / ".grokbuild-proxy", grok_wanted, "grokbuild-proxy")
    print()
    print("下一步：复制 templates 里的示例配置，完成 OAuth 登录，再:")
    print("  python3 scripts/bridge.py install grok|gemini|codex")
    print("  python3 scripts/bridge.py install restore")
    return 0


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ZCode LLM Bridge 跨平台工具（体检 / 安装 / 巡检 / 下载二进制）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="陌生人视角体检：缺什么会直接告诉你")
    inst = sub.add_parser("install", help="安装自愈任务和/或本地代理常驻")
    inst.add_argument("target", nargs="?", default="restore", choices=("restore", "grok", "gemini", "codex", "all"))
    sub.add_parser("uninstall", help="卸载本项目注册的调度任务")
    sub.add_parser("status", help="端口 + HTTP + 调度器巡检")
    rst = sub.add_parser("restart", help="重启常驻任务")
    rst.add_argument("target", nargs="?", default="all", choices=("all", "grok", "gemini", "codex", "restore"))
    sub.add_parser("logs", help="打印各通道最近日志")
    sub.add_parser("fetch", help="从 GitHub Releases 下载 CLIProxyAPI 与 grokbuild-proxy")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "doctor": cmd_doctor,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
        "logs": cmd_logs,
        "fetch": cmd_fetch,
    }
    if args.cmd == "install":
        return cmd_install(args.target)
    if args.cmd == "restart":
        return cmd_restart(args.target)
    return commands[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
