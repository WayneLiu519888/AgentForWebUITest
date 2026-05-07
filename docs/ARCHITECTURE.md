# AgentForWebUITest — 架构文档

> v0.5.0 (迭代1-5) — 自主Web UI测试Agent

---

## 整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                    AgentForWebUITest v0.5.0                     │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CLI:  webui-test check | test | explore | suite               │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Strategy  │─▶│ Explorer │─▶│ Planner  │─▶│ Executor │─▶Rep  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│       │             │              │              │             │
│       ▼             ▼              ▼              ▼             │
│  ┌────────────────────────────────────────────────────┐        │
│  │              SuiteRunner (v0.5.0)                   │        │
│  │  SuiteBuilder → Filter → DependencyGraph → Runner  │        │
│  └────────────────────────────────────────────────────┘        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │          BrowserInterface (v0.5.0)                   │       │
│  │  ┌──────────────┐  ┌──────────────────────────────┐ │       │
│  │  │ AgentBrowser │  │   PlaywrightBrowser          │ │       │
│  │  │ (Chrome 147) │  │ Chromium│Firefox│WebKit      │ │       │
│  │  └──────────────┘  └──────────────────────────────┘ │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
├────────────────────────────────────────────────────────────────┤
│  基础设施: agent-browser CLI · Playwright · pyyaml              │
└────────────────────────────────────────────────────────────────┘
```

---

## 核心模块

### 1. StrategyEngine (`strategy.py`, 114行)

解析自然语言指令为结构化测试策略。

支持模式: 快速/深度/登录/完整

### 2. Explorer (`explorer.py`, 283行)

BFS递归页面探索，自动发现链接、表单、API端点。

产出: KnowledgeGraph

### 3. TestCasePlanner (`planner.py`, 768行)

从知识图谱自动生成测试用例。

5类用例: form / button / link / api / page

### 4. TestExecutor (`executor.py`, 696行)

ReAct循环执行: Observe → Think → Act → Verify

### 5. SelectorHealer (`healer.py`)

自愈选择器: 元素定位失败时自动降级策略 (xpath→css→text→aria-label)

### 6. Judge (`judge.py`, 1226行)

多模态判定: Pass / Fail / Partial

### 7. Analyzer (`analyzer.py`, 1371行)

根因分析 + 趋势报告 + Bug报告

### 8. TestReporter (`reporter.py`, 834行)

Markdown报告 + JSON导出

---

## v0.5.0 新增模块

### SuiteRunner (`suite/runner.py`)

套件编排执行器，支持串行/并行 + CI退出码。

### SuiteBuilder (`suite/builder.py`)

8个预置模板: smoke / critical / regression / full / api / form / ui / a11y

### Filter (`suite/filter.py`)

过滤表达式: `P0+form` / `~P3` / `url:/login/`

### BrowserInterface (`browser/interface.py`)

抽象基类，统一 agent-browser 和 Playwright 接口。

### JUnitReport (`suite/junit.py`)

标准 JUnit XML 生成，兼容 GitHub Actions / Jenkins。

---

## 数据流

```
用户指令
  → StrategyEngine.parse()  → TestStrategy
  → Explorer.explore()      → KnowledgeGraph
  → Planner.plan()          → [TestCase, ...]
  → SuiteBuilder.build()    → [TestSuite, ...]
  → SuiteRunner.run()       → [SuiteResult, ...]
  → JUnitReport.generate()  → junit.xml (CI)
  → Reporter.generate()     → test_report.md
```
