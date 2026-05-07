# AgentForWebUITest — 迭代5：TestSuite + CI集成 + 多浏览器

> **制定日期**: 2026-05-07
> **当前版本**: v0.4.0 (迭代1-4完成 + 工程化)
> **迭代目标**: 让AgentForWebUITest从"能跑"到"生产可用的测试框架"

---

## 一、当前状态基线

### 1.1 已完成的模块

| 模块 | 文件 | 行数 | 职责 |
|------|------|:--:|------|
| 主入口 | `agent.py` | 410 | 5-Phase流水线: 策略→探索→规划→执行→报告 |
| 策略引擎 | `strategy.py` | 114 | 4种指令格式解析 (快速/深度/登录/完整) |
| 探索引擎 | `explorer.py` | 283 | BFS递归探索、同源过滤、API拦截 |
| 用例生成 | `planner.py` | 768 | 5类用例: form/button/link/api/page |
| 执行引擎 | `executor.py` | 696 | ReAct循环: Observe→Think→Act→Verify |
| 自愈选择器 | `healer.py` | — | 元素定位失败自动修复 |
| 判定引擎 | `judge.py` | 1226 | 多模态判定: Pass/Fail/Partial |
| 根因分析 | `analyzer.py` | 1371 | 失败分析、趋势报告、Bug报告 |
| 报告生成 | `reporter.py` | 834 | Markdown报告生成 |
| 浏览器驱动 | `browser/driver.py` | 336 | agent-browser CLI封装 (仅Chrome) |
| 知识图谱 | `knowledge/graph.py` | 237 | 页面知识结构化存储 |
| **合计** | **11** | **~6350** | |

### 1.2 关键指标

| 指标 | 当前值 | 迭代5目标 |
|------|--------|:---------:|
| 测试用例数 | 9 | ≥25 |
| 浏览器支持 | Chrome (agent-browser) | Chrome + Playwright(Firefox/WebKit) |
| CI可用性 | ❌ 无 | ✅ JUnit XML + exit codes |
| 测试套件 | ❌ 按发现顺序 | ✅ 可编排/过滤/优先级执行 |
| 测试通过率 | 100% (9/9 单元) | 100% |
| 包发布 | ❌ 未发布 | ✅ PyPI (agent-for-webui-test) |

---

## 二、迭代5 设计目标

```
用户视角:
  webui-test suite test --browser firefox --ci         ← CI模式，Firefox执行
  webui-test suite report --format junit                ← JUnit XML 可被Jenkins/GitHub解析
  webui-test suite plan --filter "P0+form"              ← 只测核心表单
  webui-test check --browser all                        ← 自检所有浏览器

CI视角:
  webui-test suite run --ci                             ← 退出码=失败数
  → report ci: writes JUnit XML + 归档截图
  → exit 0 (全绿) / exit N (N个失败)
  → GitHub Actions / Jenkins 直接集成
```

---

## 三、任务分组与详细设计

### 📦 组A：TestSuite 组装引擎 (P1, 预计 8h)

#### A1. 设计理念

当前 `executor.execute_all()` 按发现顺序线性执行所有用例。TestSuite 提供：

- **套件定义** — 用例分组为一个或多个套件（如 `smoke` / `regression` / `api`）
- **优先级过滤** — `--filter "P0+P1"` 只跑核心用例
- **类别过滤** — `--filter "form+api"` 只测表单和API
- **排序策略** — P0→P1→P2→P3 或 依赖拓扑排序
- **依赖标记** — 用例间声明前置依赖（如 "登录成功" → "修改密码"）
- **并行执行** — 独立套件并行跑

#### A2. 新增文件

```
src/
├── suite/                      # 新增: TestSuite 模块
│   ├── __init__.py
│   ├── builder.py              # SuiteBuilder: 从 cases 构建套件
│   ├── runner.py               # SuiteRunner: 执行套件，收集结果
│   ├── filter.py               # 过滤表达式解析器
│   └── dependency.py           # 依赖图解析 + 拓扑排序
```

#### A3. SuiteBuilder — 套件构建器

```python
@dataclass
class TestSuite:
    """测试套件"""
    name: str                    # "smoke" / "regression" / "api"
    cases: List[TestCase]        # 套件包含的用例
    dependencies: Dict[str, List[str]]  # case_id → [前置case_id, ...]
    parallel: bool = False       # 是否可并行
    metadata: dict = field(default_factory=dict)

class SuiteBuilder:
    """从用例列表自动构建套件"""
    
    # 预置套件模板
    PRESETS = {
        "smoke":     {"priorities": ["P0"], "max_cases": 10},
        "regression": {"priorities": ["P0", "P1", "P2"], "max_cases": 50},
        "full":      {"priorities": ["P0", "P1", "P2", "P3"]},
        "api":       {"categories": ["api"]},
        "form":      {"categories": ["form"]},
        "a11y":      {"categories": ["page"], "tags": ["accessible"]},
    }
    
    def build(self, cases: List[TestCase], 
              preset: str = "regression",
              filter_expr: str = None) -> List[TestSuite]:
        """
        1. 应用 filter_expr 过滤用例
        2. 按依赖拓扑排序
        3. 分组为套件（按类别/优先级）
        """
        ...
```

#### A4. SuiteRunner — 套件执行器

```python
@dataclass
class SuiteResult:
    """套件执行结果"""
    suite_name: str
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_skipped: int
    pass_rate: float
    duration_ms: int
    case_results: List[TestExecutionResult]
    suite_report_path: str

class SuiteRunner:
    """套件执行器 — 支持串行/并行"""
    
    def __init__(self, executor: TestExecutor, max_workers: int = 1):
        self.executor = executor
        self.max_workers = max_workers
    
    def run(self, suites: List[TestSuite], 
            parallel: bool = False) -> List[SuiteResult]:
        """
        执行所有套件:
        - 非并行: 按套件顺序，套件内按依赖顺序
        - 并行: 独立套件用 ThreadPoolExecutor 并发
        - 有依赖的套件串行执行
        """
        ...

    def run_single(self, suite: TestSuite) -> SuiteResult:
        """执行单个套件"""
        for case in self._resolve_order(suite):
            result = self.executor.execute_test_case(case)
            ...
```

#### A5. 过滤表达式解析器

```
语法:
  P0+P1              → 优先级 P0 和 P1
  form+api           → 类别 form 和 api  
  P0+form            → P0 且 form 类别
  ~P3                → 排除 P3
  url:/login/        → URL 包含 /login/ 的页面用例

Filter.parse("P0+form") → Filter(priorities={"P0"}, categories={"form"})
Filter.parse("P0+P1+api,~P3") → 组合过滤
```

---

### 🔧 组B：CI/CD 集成 (P1, 预计 6h)

#### B1. CI 模式

```bash
webui-test suite run --ci           # CI模式
webui-test suite run --ci --browser firefox --filter "P0"
```

CI 模式特性：

| 特性 | 非CI模式 | CI模式 |
|------|:-------:|:-----:|
| 输出格式 | 彩色终端 | 纯文本 + JUnit XML |
| 日志级别 | INFO | WARNING（减少噪音） |
| 退出码 | 总是0 | 失败数（0=全绿） |
| 截图保留 | reports/按时间戳 | ci-artifacts/固定路径 |
| 浏览器 | headed (交互) | headless (无头) |
| 超时策略 | 宽容 | 严格 (CI timeout短) |

#### B2. JUnit XML 报告

```python
# src/suite/junit.py
class JUnitReport:
    """生成 JUnit XML 格式报告
    
    可被 GitHub Actions, Jenkins, GitLab CI 直接解析。
    """
    
    def generate(self, suite_results: List[SuiteResult]) -> str:
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <testsuites>
          <testsuite name="smoke" tests="5" failures="0" time="12.3">
            <testcase name="TC-F-1: 登录-正常提交" time="2.1">
              <system-out>截图: ci-artifacts/screenshot_TC-F-1.png</system-out>
            </testcase>
            <testcase name="TC-A-3: GET /api/users" time="0.3">
              <failure message="状态码不匹配">
                预期: 200, 实际: 500
              </failure>
            </testcase>
          </testsuite>
        </testsuites>
        """
        ...
```

#### B3. CI 退出码策略

```python
def ci_exit_code(results: List[SuiteResult]) -> int:
    """计算CI退出码
    - 0: 全部通过
    - N: N个失败 (0 < N ≤ 255)
    - 255: 执行过程中崩溃 (max exit code)
    """
    failed = sum(r.cases_failed for r in results)
    return min(failed, 255)
```

#### B4. GitHub Actions 集成示例

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on: [push, pull_request]
jobs:
  webui-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install agent-for-webui-test
      - run: webui-test check
      - run: webui-test suite run --ci --filter "P0" --browser chromium
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: webui-test-results
          path: ci-artifacts/
      - uses: dorny/test-reporter@v1
        if: always()
        with:
          name: WebUI Tests
          path: ci-artifacts/junit.xml
          reporter: java-junit
```

---

### 🧪 组C：多浏览器支持 (P1, 预计 10h)

#### C1. 架构设计

```
现有: AgentBrowser (硬编码 agent-browser CLI → Chrome 147)

重构为:
                    ┌──────────────────────┐
                    │   BrowserInterface    │  ← 抽象接口
                    │   (Protocol / ABC)    │
                    └──────────┬───────────┘
           ┌───────────────────┼───────────────────────┐
           ▼                   ▼                       ▼
  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────────┐
  │ AgentBrowser    │ │ PlaywrightChrome│ │ PlaywrightFirefox│
  │ (现有实现)      │ │ (新增)          │ │ (新增)           │
  └────────┬────────┘ └────────┬────────┘ └────────┬─────────┘
           │                   │                     │
           ▼                   ▼                     ▼
    agent-browser CLI    Playwright API       Playwright API
    (Chrome 147)         (Chromium)           (Firefox)
```

#### C2. BrowserInterface 抽象协议

```python
# src/browser/interface.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

class BrowserInterface(ABC):
    """浏览器驱动抽象接口 — 任何浏览器后端必须实现"""
    
    @abstractmethod
    def navigate(self, url: str) -> bool: ...
    
    @abstractmethod
    def snapshot(self, interactive_only: bool = True) -> Dict: ...
    
    @abstractmethod
    def click(self, ref: str) -> bool: ...
    
    @abstractmethod
    def fill(self, ref: str, text: str) -> bool: ...
    
    @abstractmethod
    def screenshot(self, path: str = None, annotate: bool = False) -> str: ...
    
    @abstractmethod
    def eval_js(self, js_code: str) -> Any: ...
    
    @abstractmethod
    def extract_elements(self) -> List[Dict]: ...
    
    @abstractmethod
    def close(self): ...
    
    # 新方法 (多浏览器需要)
    @abstractmethod
    def get_browser_info(self) -> Dict: ...  # {"name": "Chrome", "version": "147", "engine": "Blink"}
```

#### C3. Playwright 后端实现

```python
# src/browser/playwright_driver.py
class PlaywrightBrowser(BrowserInterface):
    """基于 Playwright 的跨浏览器驱动
    
    支持: Chromium, Firefox, WebKit
    """
    
    def __init__(self, browser_type: str = "chromium", headless: bool = True):
        self.browser_type = browser_type  # chromium, firefox, webkit
        self.playwright = None
        self.browser = None
        self.page = None
        
    def navigate(self, url: str) -> bool:
        if not self.page:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            browser_launcher = getattr(self.playwright, self.browser_type)
            self.browser = browser_launcher.launch(headless=self.headless)
            self.page = self.browser.new_page()
        self.page.goto(url)
        return True
    
    def snapshot(self, interactive_only: bool = True) -> Dict:
        """生成与 agent-browser 兼容的快照格式"""
        js = """
        // 生成交互元素列表
        (() => {
            const elements = [];
            document.querySelectorAll(
                'a[href],button,input,select,textarea,[role="button"],[onclick]'
            ).forEach((el, i) => {
                const tag = el.tagName.toLowerCase();
                const text = (el.textContent || el.value || el.placeholder || '').trim().substring(0, 50);
                elements.push(`[ref=e${i+1}] <${tag}> ${text}`);
            });
            return elements.join('\\n');
        })()
        """
        result = self.page.evaluate(js)
        return {"snapshot": result, "refs": self._parse_refs(result)}
    
    def click(self, ref: str) -> bool:
        idx = int(ref.replace("@e", "")) - 1
        selector = f"document.querySelectorAll('a[href],button,input,select,textarea,[role=\"button\"],[onclick]')[{idx}].click()"
        self.page.evaluate(selector)
        return True
    
    def get_browser_info(self) -> Dict:
        return {
            "name": self.browser_type.capitalize(),
            "engine": {"chromium": "Blink", "firefox": "Gecko", "webkit": "WebKit"}[self.browser_type],
            "backend": "Playwright",
        }
```

#### C4. 浏览器工厂

```python
# src/browser/factory.py
def create_browser(name: str, headless: bool = True, **kwargs) -> BrowserInterface:
    """浏览器工厂
    
    Args:
        name: "chrome" | "firefox" | "webkit" | "agent-browser"
    """
    if name in ("chrome", "chromium"):
        from .playwright_driver import PlaywrightBrowser
        return PlaywrightBrowser(browser_type="chromium", headless=headless)
    
    if name == "firefox":
        from .playwright_driver import PlaywrightBrowser
        return PlaywrightBrowser(browser_type="firefox", headless=headless)
    
    if name == "webkit":
        from .playwright_driver import PlaywrightBrowser
        return PlaywrightBrowser(browser_type="webkit", headless=headless)
    
    if name == "agent-browser":
        from .driver import AgentBrowser, BrowserConfig
        return AgentBrowser(BrowserConfig(headless=headless))
    
    raise ValueError(f"不支持的浏览器: {name}")
```

#### C5. Agent 层改造

```python
# agent.py 修改
class WebUITestAgent:
    def run(self, instruction: str, browser_name: str = "chrome", ...):
        # 替换硬编码的 AgentBrowser 初始化
        self.browser = create_browser(browser_name, headless=True)
```

#### C6. CLI 新增参数

```bash
webui-test suite run --browser firefox      # Firefox
webui-test suite run --browser webkit        # Safari/WebKit
webui-test suite run --browser chrome        # Chrome (Playwright)
webui-test suite run --browser agent-browser  # 现有 agent-browser CLI
webui-test check --browser all               # 检查所有浏览器可用性
```

---

### 📊 组D：测试增强与文档 (P2, 预计 6h)

#### D1. 测试套件

| 新增测试文件 | 内容 | 用例 |
|-------------|------|:--:|
| `tests/test_suite_builder.py` | SuiteBuilder + 预设模板 | 8 |
| `tests/test_suite_runner.py` | SuiteRunner 串行/并行 | 6 |
| `tests/test_filter_parser.py` | 过滤表达式解析 | 10 |
| `tests/test_junit_report.py` | JUnit XML 生成/验证 | 4 |
| `tests/test_browser_interface.py` | BrowserInterface 协议合规 | 5 |
| `tests/test_playwright_driver.py` | Playwright 多浏览器 | 6 |

#### D2. 配置扩展

```yaml
# config.yaml 新增
suite:
  default_preset: regression
  parallel: false
  max_workers: 1
  exit_on_first_failure: false

browsers:
  default: chrome
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

ci:
  junit_path: ci-artifacts/junit.xml
  screenshot_dir: ci-artifacts/screenshots
  exit_code_mode: fail_count   # fail_count | boolean
  verbose: false
```

---

## 四、实施计划与时间线

```
总工时: ~30h
建议周期: 1.5周 (7个工作日)

Day 1-2: 组A 套件引擎         ████████ 8h
Day 3-4: 组C 多浏览器驱动      ██████████ 10h  (可与B并行)
Day 4-5: 组B CI集成            ██████ 6h        (可与C并行)
Day 6-7: 组D 测试+文档         ██████ 6h
Day 7:   集成验证+发布         ██ 2h
```

### 任务依赖图

```
组A (Suite)  ──→ 组B (CI)    [CI需要Suite的SuiteResult]
组A (Suite)  ──→ 组D (测试)  [测试Suite模块]
组C (多浏览器) → 组B (CI)    [CI需要多浏览器支持]
组C (多浏览器) → 组D (测试)  [测试Playwright驱动]

组C 可与 组A 并行开发，组B 可与 组C 并行开发。
```

---

## 五、交付物清单

### 新增文件 (10个)

| 文件 | 行数(估) | 用途 |
|------|:---:|------|
| `src/suite/__init__.py` | 30 | 套件模块入口 |
| `src/suite/builder.py` | 250 | SuiteBuilder + 预设模板 |
| `src/suite/runner.py` | 200 | SuiteRunner 串行/并行 |
| `src/suite/filter.py` | 150 | 过滤表达式解析 |
| `src/suite/dependency.py` | 120 | 依赖拓扑排序 |
| `src/browser/interface.py` | 80 | BrowserInterface 抽象协议 |
| `src/browser/playwright_driver.py` | 350 | Playwright 多浏览器实现 |
| `src/browser/factory.py` | 60 | 浏览器工厂 |
| `src/suite/junit.py` | 120 | JUnit XML 生成 |
| `src/suite/ci.py` | 80 | CI模式入口 |

### 新增测试文件 (6个)

| 文件 | 用例 |
|------|:--:|
| `tests/test_suite_builder.py` | 8 |
| `tests/test_suite_runner.py` | 6 |
| `tests/test_filter_parser.py` | 10 |
| `tests/test_junit_report.py` | 4 |
| `tests/test_browser_interface.py` | 5 |
| `tests/test_playwright_driver.py` | 6 |

### 修改文件 (5个)

| 文件 | 变更 |
|------|------|
| `src/agent.py` | 支持 `browser_name` 参数，集成 SuiteRunner |
| `src/cli.py` | 新增 `suite` 子命令，`--browser`/`--ci`/`--filter` 参数 |
| `config.yaml` | 新增 suite/browsers/ci 配置段 |
| `requirements.txt` | 新增 `playwright` 可选依赖 |
| `pyproject.toml` | 新增 `playwright` 可选依赖组，版本 → 0.5.0 |

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:--:|------|---------|
| Playwright 安装失败 (系统依赖) | 中 | 高 | 保留 agent-browser 作为 fallback，Playwright 设为可选依赖 |
| agent-browser snapshot 与 Playwright 快照格式不兼容 | 中 | 中 | BrowserInterface 规定统一输出格式，各后端自行适配 |
| 套件依赖拓扑排序复杂度 | 低 | 中 | 限制依赖深度 ≤3，循环检测 |
| CI 模式下超时不够 | 中 | 中 | 可配置 timeout，提供 `--ci-timeout` 参数 |
| Firefox/WebKit 行为差异 | 中 | 中 | 预期差异（已知差异），judge 容差放宽 |

---

## 七、v0.5.0 Release 检查清单

### 代码

- [ ] SuiteBuilder 4个预置模板可用
- [ ] SuiteRunner 串行/并行执行正常
- [ ] 过滤表达式 `P0+form` / `~P3` / `url:/login/` 正确
- [ ] JUnit XML 可被 GitHub Actions test-reporter 解析
- [ ] CI 模式退出码 = 失败数
- [ ] Playwright Chromium 快照格式与 agent-browser 兼容
- [ ] Playwright Firefox 基本可用
- [ ] browser_factory 正确路由 4 种后端

### 测试

- [ ] 新增 39 个测试用例全部通过
- [ ] 回归: 现有 9 个测试无破坏

### 文档

- [ ] README 更新迭代5特性
- [ ] config.yaml 完整注释
- [ ] CI 集成示例 (GitHub Actions)

### 发布

- [ ] 版本号 0.4.0 → 0.5.0
- [ ] PyPI 发布 agent-for-webui-test v0.5.0
- [ ] `pip install "agent-for-webui-test[playwright]"` 可用
