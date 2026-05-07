# AgentForWebUITest

> **告诉 Agent 测试哪个系统，Agent 自主完成全流程 Web UI 测试**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]
[![Tests](https://img.shields.io/badge/tests-9%20passed-brightgreen)]
[![Version](https://img.shields.io/badge/version-0.5.0-blue)]

---

## ⚡ 5 秒安装

```bash
pip install agent-for-webui-test && webui-test check
```

---

## 🎯 一句话描述

**AI 自主 Web UI 测试 Agent** — 从页面探索、用例生成、执行判定到报告输出，全流程无人值守。

---

## 🧭 快速了解

| | | | |
|:---:|:---:|:---:|:---:|
| 🔍 **自主探索** | 🧪 **智能用例** | ⚡ **ReAct执行** | 🏗️ **TestSuite** |
| BFS递归爬取页面 | 5类用例自动生成 | 自愈选择器 | 过滤+依赖编排 |
| API拦截+知识图谱 | P0-P3优先级 | 失败重试 | 8个预置模板 |

---

## 🏗️ 架构总览

```
用户指令 → Strategy → Explorer → Planner → SuiteRunner → 报告
                          │          │           │
                    KnowledgeGraph  [TestCase]  SuiteResult
                          │          │           │
                    ┌──────┴──────────┴───────────┴──────┐
                    │        BrowserInterface             │
                    │  AgentBrowser │ PlaywrightBrowser   │
                    │  (Chrome 147)  │ (Chromium|FF|WK)   │
                    └─────────────────────────────────────┘
```

---

## 🚀 快速上手

```bash
# 1. 安装
pip install agent-for-webui-test

# 2. 自检
webui-test check

# 3. 冒烟测试
webui-test suite https://httpbin.org --preset smoke

# 4. CI 模式
webui-test suite https://example.com --ci --filter "P0+P1"
```

```python
# Python API
from src.agent import WebUITestAgent

agent = WebUITestAgent()
result = agent.run_with_suite("测试 https://example.com", preset="smoke")
print(f"通过率: {result['suite_summary']['pass_rate']}%")
```

---

## 📊 项目状态

| 迭代 | 内容 | 状态 |
|------|------|:--:|
| 迭代1 | 自主探索 + 知识图谱 | ✅ |
| 迭代2 | 智能用例生成 (5类) | ✅ |
| 迭代3 | ReAct执行 + 自愈选择器 | ✅ |
| 迭代4 | 智能判定 + 根因分析 | ✅ |
| 迭代5 | TestSuite + CI集成 + 多浏览器 | ✅ |

| 模块 | 文件 | 行数 |
|------|:--:|:--:|
| 核心引擎 | 9 | ~4,800 |
| TestSuite | 6 | ~750 |
| 浏览器驱动 | 4 | ~750 |
| 工具 | 5 | ~1,500 |
| 测试 (9用例) | 6 | ~600 |
| **合计** | **29** | **~8,500** |

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [快速上手](docs/QUICKSTART.md) | 5分钟从零到使用 |
| [安装指南](docs/INSTALLATION.md) | pip + Docker 多路径 |
| [架构文档](docs/ARCHITECTURE.md) | 架构详解 |
| [配置参考](docs/CONFIGURATION.md) | 完整参数说明 |
| [日志调试](docs/LOGGING.md) | 日志与调试 |
| [发版清单](docs/RELEASE_CHECKLIST.md) | 发布检查 |

---

## 🔧 CLI 命令

```bash
webui-test check                              # 环境自检
webui-test test <url>                         # 完整测试
webui-test explore <url>                      # 仅探索
webui-test suite <url>                        # TestSuite 编排
webui-test suite <url> --preset smoke         # 冒烟测试
webui-test suite <url> --filter "P0+form"     # 过滤执行
webui-test suite <url> --ci                   # CI模式
webui-test version                            # 版本信息
```

---

## 🧪 测试

```bash
pytest tests/ -v    # 9 passed
make test           # 等效
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| **v0.5.0** | 2026-05-07 | TestSuite + CI + 多浏览器 + 文档完善 |
| v0.4.0 | 2026-05-07 | 工程化: pip/CLI/CI/Makefile |
| v0.3.0 | 2026-04-28 | 迭代1-4: 探索/用例/执行/判定 |
| v0.2.0 | 2026-04-26 | 迭代1-2: 探索 + 用例生成 |
| v0.1.0 | 2026-04-26 | 项目初始化 |
