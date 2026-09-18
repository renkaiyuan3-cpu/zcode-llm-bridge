# Windows helpers

这些 `.ps1` 只是 `scripts/bridge.py` 的薄包装。完整说明请看 [docs/windows-guide.md](../docs/windows-guide.md)。

```powershell
py -3 ..\scripts\bridge.py doctor
powershell -ExecutionPolicy Bypass -File .\fetch-binaries.ps1
powershell -ExecutionPolicy Bypass -File .\install-runtime.ps1 -Target restore
powershell -ExecutionPolicy Bypass -File .\service-manager.ps1 status
```
