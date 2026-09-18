# 从 GitHub Releases 下载 CLIProxyAPI 与 grokbuild-proxy 到用户主目录。
# 用法:
#   powershell -ExecutionPolicy Bypass -File .\windows\fetch-binaries.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Bridge = Join-Path $RepoRoot "scripts\bridge.py"

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & py -3 $Bridge fetch
} else {
    & python $Bridge fetch
}
exit $LASTEXITCODE
