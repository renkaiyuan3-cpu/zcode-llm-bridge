<!-- 提交前自查（详见 CONTRIBUTING.md 第 6 节） -->

**这个 PR 做了什么**

**类型**
- [ ] 新供应商接入
- [ ] 文档修正（上游接口变化等）
- [ ] 脚本 / 工具改进
- [ ] 其他

**自查清单**
- [ ] `grep -rE "sk-[a-zA-Z0-9]{20,}" .` 无真实凭据，无个人路径 / UUID
- [ ] 档位取值域经过实测，证据写进了注释或文档
- [ ] 新增 apply 脚本已登记进 `restore-reasoning.py`，并提示重跑 `python3 scripts/bridge.py install restore`
- [ ] 幂等性验证过：同一脚本连跑两次，第二次输出「已是最新」
- [ ] README 对照表 / 快速开始 / 端口表已同步更新
