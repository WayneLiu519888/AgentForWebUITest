# AgentForWebUITest — 日志与调试指南

---

## 概述

AgentForWebUITest 使用 Python 标准 `logging` 模块，按模块层级输出结构化日志。

---

## 日志层级

| Level | 用途 | 示例 |
|:-----:|------|------|
| **INFO** | 正常流程进度 | `[Explorer] 探索 https://example.com` |
| **WARNING** | 可恢复异常 | `[Healer] 选择器降级: xpath→text_content` |
| **ERROR** | 操作失败 | `[Executor] 用例 TC-F-1 步骤3失败` |
| **DEBUG** | 开发调试 | `[Browser] snapshot返回 245 元素` |

---

## 启用日志

### 命令行方式

```bash
# 调试模式
webui-test suite https://example.com --debug

# 或通过环境变量
export WEBUI_LOG_LEVEL=DEBUG
webui-test suite https://example.com
```

### Python 代码方式

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from src.agent import WebUITestAgent
agent = WebUITestAgent()
agent.run("测试 https://example.com")
```

---

## 日志输出

```
2026-05-07 15:30:01 INFO     src.agent              AgentForWebUITest v0.5.0 初始化
2026-05-07 15:30:01 INFO     src.strategy           策略解析: mode=quick depth=2
2026-05-07 15:30:02 INFO     src.explorer           探索 [0/2]: https://example.com
2026-05-07 15:30:05 INFO     src.explorer             发现: 41 元素, 5 链接, 3 API
2026-05-07 15:30:05 INFO     src.planner            生成 12 个测试用例
2026-05-07 15:30:06 WARNING  src.healer             选择器降级: #login-btn → aria-label
2026-05-07 15:30:08 INFO     src.suite.runner        套件 smoke: ✅ 5/5 passed
```

---

## 日志到文件

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
    handlers=[
        logging.FileHandler("webui-test.log"),
        logging.StreamHandler()
    ]
)
```

---

## 常见调试技巧

### 1. 查看浏览器快照

```python
browser = create_browser("agent-browser")
browser.navigate("https://example.com")
snap = browser.snapshot()
print(snap["snapshot"])  # 页面交互元素
print(snap["refs"])      # ref映射表
```

### 2. 查看浏览器控制台

```python
browser.eval_js("console.log('hello'); return 'ok'")
# 然后查看 agent-browser 输出
```

### 3. 保存执行截图

```yaml
# config.yaml
executor:
  screenshot_on_step: true
  screenshot_on_fail: true
  screenshot_dir: reports/debug_screenshots
```
