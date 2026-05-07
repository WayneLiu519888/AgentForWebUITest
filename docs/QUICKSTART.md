# AgentForWebUITest — 5分钟上手

> 告诉Agent测试哪个系统 → Agent自主完成探索、用例生成、执行、判定

---

## 前提条件

- Python 3.9+
- Chrome/Chromium (或使用 Playwright 的 Firefox/WebKit)
- agent-browser CLI (Chrome 模式) 或 `playwright` (多浏览器模式)

---

## 步骤 1：安装 (10秒)

```bash
pip install agent-for-webui-test
```

多浏览器支持 (可选):

```bash
pip install "agent-for-webui-test[playwright]"
playwright install chromium
```

---

## 步骤 2：环境自检 (5秒)

```bash
webui-test check
```

期望输出:
```
✅ Python 3.12.3 ≥ 3.9
✅ pyyaml v6.0.1
✅ agent-browser 0.26.0
✅ Chrome 147.0
✅ config.yaml
✅ src.suite
🎉 环境就绪，可以正常使用
```

---

## 步骤 3：一键测试 (30秒)

```bash
# 完整测试流程 (探索→用例→执行→报告)
webui-test test https://httpbin.org

# TestSuite 编排测试
webui-test suite https://httpbin.org --preset smoke
```

期望输出:
```
[Phase 1/5] 解析策略
[Phase 2/5] 探索系统 → 2 页面
[Phase 3/5] 生成用例 → 20 个
[Phase 4/5] 执行测试
[Phase 5/5] 生成报告

✅ 完成! 耗时 18.5s
```

---

## 步骤 4：Python API

```python
from src.agent import WebUITestAgent

agent = WebUITestAgent()

# 完整流程
result = agent.run("测试 https://httpbin.org")

# TestSuite 模式
result = agent.run_with_suite(
    "测试 https://httpbin.org",
    preset="regression",
    filter_expr="P0+form"
)

# 查看结果
print(f"探索: {result['pages_explored']} 页面")
print(f"用例: {result['test_case_count']} 个")
print(f"套件: {result.get('suite_summary', {})}")
```

---

## 步骤 5：CI 集成

```bash
# GitHub Actions / Jenkins
webui-test suite https://example.com --ci --filter "P0+P1"

# 产生 ci-artifacts/junit.xml
# 退出码 = 失败数 (0 = 全绿)
```

---

## 常用命令速查

| 命令 | 说明 |
|------|------|
| `webui-test check` | 环境自检 |
| `webui-test test <url>` | 完整测试 |
| `webui-test explore <url>` | 仅探索 |
| `webui-test suite <url>` | TestSuite 编排 |
| `webui-test suite <url> --preset smoke` | 冒烟测试 |
| `webui-test suite <url> --filter "P0+form"` | 过滤执行 |
| `webui-test suite <url> --ci` | CI 模式 |

---

## 下一步

- 📖 [安装指南](INSTALLATION.md) — pip + Docker 多路径安装
- 🏗️ [架构文档](ARCHITECTURE.md) — 架构详解
- ⚙️ [配置说明](CONFIGURATION.md) — 完整参数
- 📋 [日志指南](LOGGING.md) — 调试技巧
