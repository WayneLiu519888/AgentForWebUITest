# AgentForWebUITest — 配置参考

> 完整配置参数说明 (config.yaml)

---

## 配置加载

```python
# 默认: ./config.yaml
agent = WebUITestAgent()

# 指定路径
agent = WebUITestAgent(config_path="/path/to/custom.yaml")
```

---

## 完整配置参考

```yaml
# config.yaml — AgentForWebUITest 完整配置

# ═══════════════════════════════════════════════════
# 浏览器配置
# ═══════════════════════════════════════════════════
browser:
  binary: "/root/.hermes/node/bin/agent-browser"  # agent-browser CLI 路径
  headless: true                                   # 无头模式 (CI必须true)
  session_name: "webui-test"                       # 浏览器会话名
  default_timeout: 30                              # 默认命令超时(秒)

# ═══════════════════════════════════════════════════
# 探索配置
# ═══════════════════════════════════════════════════
explorer:
  max_depth: 3               # 递归最大深度
  max_pages: 50              # 最多探索页面数
  same_origin_only: true     # 仅同源页面
  wait_after_load_ms: 1000   # 页面加载后等待(ms)
  element_timeout_ms: 5000   # 元素等待超时(ms)

# ═══════════════════════════════════════════════════
# 用例生成配置
# ═══════════════════════════════════════════════════
planner:
  cases_per_page: 10                   # 每页默认用例数
  priority_distribution:               # 优先级分布
    P0: 20   # 核心流程 (页面加载, 登录)
    P1: 30   # 重要功能 (API状态码, 按钮)
    P2: 30   # 边界测试 (空值, 特殊字符)
    P3: 20   # 探索性 (可见性, 标题)

# ═══════════════════════════════════════════════════
# 执行器配置
# ═══════════════════════════════════════════════════
executor:
  use_browser: false              # 是否实际启动浏览器 (测试时false)
  screenshot_on_step: true        # 每步截图
  screenshot_on_fail: true        # 失败时截图
  screenshot_dir: "reports/screenshots"
  max_retries_per_step: 2         # 步骤最大重试
  step_timeout_ms: 30000          # 步骤超时
  wait_after_action_ms: 1000      # 操作后等待
  verify_timeout_ms: 5000         # 验证超时
  skip_on_first_failure: false    # 首失败跳过
  continue_on_failure: true       # 失败后继续
  enable_healing: true            # 自愈选择器
  verbose: true                   # 详细输出

# ═══════════════════════════════════════════════════
# 套件配置
# ═══════════════════════════════════════════════════
suite:
  default_preset: regression      # smoke|critical|regression|full
  parallel: false                 # 并行执行
  max_workers: 1                  # 最大工作线程

# ═══════════════════════════════════════════════════
# 多浏览器配置 (v0.5.0+)
# ═══════════════════════════════════════════════════
browsers:
  default: chrome                 # chrome|firefox|webkit|agent-browser
  chrome:
    type: playwright_chromium
    headless: true
  firefox:
    type: playwright_firefox
    headless: true
  webkit:
    type: playwright_webkit
    headless: true
  agent-browser:
    type: agent_browser_cli
    binary: /root/.hermes/node/bin/agent-browser
    headless: true

# ═══════════════════════════════════════════════════
# CI 配置
# ═══════════════════════════════════════════════════
ci:
  junit_path: ci-artifacts/junit.xml
  screenshot_dir: ci-artifacts/screenshots
  exit_code_mode: fail_count    # fail_count | boolean
  verbose: false

# ═══════════════════════════════════════════════════
# 报告配置
# ═══════════════════════════════════════════════════
report_dir: reports              # 报告输出目录
```

---

## 环境变量覆盖

```bash
# 浏览器二进制路径
export AGENT_BROWSER_BIN=/usr/local/bin/agent-browser

# 报告目录
export WEBUI_REPORT_DIR=./my-reports

# 默认浏览器
export WEBUI_BROWSER=firefox
```
