# AgentForWebUITest — 发版检查清单

---

## 代码质量

- [ ] 测试全部通过: `pytest tests/ -q` → `9 passed`
- [ ] CLI 自检全绿: `webui-test check` → `🎉 环境就绪`
- [ ] 无 TODO/FIXME 残留: `grep -rn "TODO|FIXME" src/`
- [ ] SuiteBuilder 8个预置模板可用
- [ ] SuiteRunner 串行/并行正常
- [ ] 过滤表达式 `P0+form` / `~P3` 正确
- [ ] JUnit XML 可被 CI 工具解析

---

## 版本一致性

| 文件 | 版本字段 | 检查 |
|------|----------|:--:|
| `pyproject.toml` | `[project] version` | |
| `src/agent.py` | `VERSION` | |
| `src/cli.py` | `VERSION` | |
| `src/reporter.py` | `agent_version` | |
| `README.md` | 版本号 | |

---

## 包发布

- [ ] `python3 -m build` 成功
- [ ] `twine check dist/*` PASSED, PASSED
- [ ] TestPyPI 安装验证: `pip install -i https://test.pypi.org/ agent-for-webui-test`
- [ ] 生产 PyPI: `twine upload dist/*`

---

## 全新环境验证

```bash
pip install agent-for-webui-test
webui-test check                      # 全部 ✅
webui-test version                    # 显示正确版本
webui-test suite --help               # 帮助正常
python -c "from src.suite import *"   # 导入正常
python -c "from src.browser import create_browser; print(create_browser('agent-browser'))"
```

---

## 文档

- [ ] README.md — 5分钟上手 + 路线图
- [ ] docs/INSTALLATION.md — 完整安装指南
- [ ] docs/QUICKSTART.md — 5步上手
- [ ] docs/CONFIGURATION.md — 配置参考
- [ ] docs/LOGGING.md — 日志调试
- [ ] docs/RELEASE_CHECKLIST.md — (本文件)

---

## 发布流程

```bash
# 1. 更新版本号 (5个文件)
#    pyproject.toml / src/agent.py / src/cli.py / src/reporter.py / README

# 2. 最终检查
make check

# 3. 构建 + 发布
make build
twine check dist/*
twine upload dist/*

# 4. Git tag
git tag "v0.5.0"
git push origin main --tags
```
