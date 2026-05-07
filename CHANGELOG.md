# AgentForWebUITest — 变更日志

## [0.5.0] — 2026-05-07

### 新增 (Added)
- **TestSuite 组装引擎** (`src/suite/`)
  - `filter.py`: 过滤表达式解析 (`P0+form`, `~P3`, `url:/login/`)
  - `dependency.py`: 依赖图拓扑排序 + 循环检测
  - `builder.py`: SuiteBuilder + 8个预置模板
  - `runner.py`: SuiteRunner 串行/并行 + CI退出码
- **CI 集成** (`src/suite/`)
  - `junit.py`: JUnit XML 生成 (GitHub Actions/Jenkins兼容)
  - `ci.py`: CIRunner CI流水线
- **多浏览器支持** (`src/browser/`)
  - `interface.py`: BrowserInterface 抽象基类
  - `playwright_driver.py`: PlaywrightBrowser (chromium/firefox/webkit)
  - `factory.py`: create_browser() 工厂路由
- **CLI 增强**: `suite` 子命令 + `--preset`/`--filter`/`--ci`/`--split` 参数
- **新增依赖**: playwright (可选, 多浏览器)
- **文档完善**: LOGGING/CONFIGURATION/QUICKSTART/RELEASE_CHECKLIST/INSTALLATION/ARCHITECTURE

### 变更 (Changed)
- 版本号: 0.4.0 → 0.5.0
- agent.py: VERSION 0.5.0, 新增 `run_with_suite()`

---

## [0.4.0] — 2026-05-07

### 新增 (Added)
- PyPI 打包 (`pyproject.toml` + `setup.py` + `MANIFEST.in`)
- CLI 命令行 (`webui-test check/test/explore/version`)
- Makefile (install/test/lint/build/check)
- `.github/workflows/ci.yml` (Python 3.9-3.13 matrix)

---

## [0.3.0] — 2026-04-28

### 新增 (Added)
- **迭代4**: Judge 判定引擎 + Analyzer 根因分析
- **迭代3**: TestExecutor ReAct执行引擎 + SelectorHealer 自愈
- TestReporter 报告生成增强

---

## [0.2.0] — 2026-04-26

### 新增 (Added)
- **迭代2**: TestCasePlanner 5类用例生成器
- **迭代1**: Explorer BFS递归探索 + KnowledgeGraph

---

## [0.1.0] — 2026-04-26

### 新增 (Added)
- 项目初始化: 骨架 + AgentBrowser 驱动
