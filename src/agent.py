"""
AgentForWebUITest — 主入口

告诉Agent测试哪个系统，Agent自主完成:
  1. 策略解析 (StrategyEngine)       ✅ 迭代1
  2. 页面探索 (Explorer)             ✅ 迭代1
  3. 用例生成 (Planner)              ✅ 迭代2
  4. 自主执行 (Executor)             ✅ 迭代3
  5. 智能判定 (Judge)               ✅ 迭代4
  6. 根因分析 (Analyzer)             ✅ 迭代4
  7. 报告生成 (Reporter)             ✅ 迭代4增强

用法:
    from src.agent import WebUITestAgent
    agent = WebUITestAgent()
    result = agent.run("测试 https://example.com")
"""

import os
import sys
from datetime import datetime

# 确保项目路径在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .strategy import StrategyEngine, TestStrategy
    from .explorer import Explorer, ExplorerConfig
    from .browser import AgentBrowser, BrowserConfig, get_browser, reset_browser
    from .knowledge import KnowledgeGraph
    from .planner import TestCasePlanner, PlannerConfig
    from .executor import TestExecutor, ExecutionConfig, TestExecutionResult
    from .judge import Judge, JudgeConfig, JudgementResult
    from .analyzer import Analyzer, FailureAnalysis, TrendReport, BugReport
    from .reporter import TestReporter
except ImportError:
    from strategy import StrategyEngine, TestStrategy
    from explorer import Explorer, ExplorerConfig
    from browser import AgentBrowser, BrowserConfig, get_browser, reset_browser
    from knowledge.graph import KnowledgeGraph
    from planner import TestCasePlanner, PlannerConfig
    from executor import TestExecutor, ExecutionConfig, TestExecutionResult
    from judge import Judge, JudgeConfig, JudgementResult
    from analyzer import Analyzer, FailureAnalysis, TrendReport, BugReport
    from reporter import TestReporter


class WebUITestAgent:
    """自主Web UI测试Agent
    
    当前: 迭代1+2+3+4 — 策略解析 + 递归探索 + 用例生成 + 自主执行 + 智能判定 + 根因分析
    后续迭代将逐步添加: 可视化报告增强
    """
    
    VERSION = "0.3.0"
    ITERATIONS = "1+2+3+4"
    
    def __init__(self, config_path: str = None):
        """初始化Agent
        
        Args:
            config_path: 配置文件路径 (默认: ./config.yaml)
        """
        self.config = self._load_config(config_path)
        self.browser = None
        self.strategy_engine = StrategyEngine()
        self.current_strategy = None
        self.knowledge_graph = None
        self.planner = None
        self.test_cases = []
        self.executor = None
        self.execution_results = []
        self.reporter = TestReporter(output_dir=self.config.get("report_dir", "reports"))
        
        print("=" * 60)
        print(f"  AgentForWebUITest v{self.VERSION} — 自主Web UI测试Agent")
        print(f"  Iteration {self.ITERATIONS}: 策略 + 探索 + 用例生成 + 自主执行")
        print("=" * 60)
    
    def run(self, instruction: str, execute: bool = True) -> dict:
        """运行自主测试
        
        Args:
            instruction: 用户指令，如 "测试 https://example.com"
            execute: 是否执行测试用例 (False=仅生成用例)
        
        Returns:
            dict: {
                "strategy": TestStrategy,
                "knowledge_graph": KnowledgeGraph,
                "test_cases": [TestCase, ...],
                "test_case_count": int,
                "execution_results": [TestExecutionResult, ...],
                "execution_summary": dict,
                "report_path": str,
                "elapsed_seconds": float,
                "pages_explored": int,
            }
        """
        start_time = datetime.now()
        
        # Phase 1: 解析策略
        print(f"\n[Phase 1/5] 解析策略: {instruction}")
        self.current_strategy = self.strategy_engine.parse(instruction)
        
        # Phase 2: 探索系统 (迭代1核心)
        print(f"\n[Phase 2/5] 探索系统...")
        self.knowledge_graph = self._run_exploration()
        
        # Phase 3: 用例生成 (迭代2核心)
        print(f"\n[Phase 3/5] 生成测试用例...")
        self.test_cases = self._run_planning()
        
        # Phase 4: 自主执行 (迭代3核心)
        print(f"\n[Phase 4/5] 自主执行测试...")
        if execute:
            self.execution_results = self._run_execution()
        else:
            print("  跳过执行 (execute=False)")
            self.execution_results = []
        
        # Phase 5: 生成报告
        print(f"\n[Phase 5/5] 生成报告...")
        report = self._generate_report()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        exec_summary = {}
        if self.executor:
            exec_summary = self.executor.get_summary_stats()
        
        result = {
            "strategy": self.current_strategy,
            "knowledge_graph": self.knowledge_graph,
            "test_cases": self.test_cases,
            "test_case_count": len(self.test_cases),
            "execution_results": self.execution_results,
            "execution_summary": exec_summary,
            "report": report,
            "elapsed_seconds": elapsed,
            "pages_explored": self.knowledge_graph.stats["total_pages"] if self.knowledge_graph else 0,
        }
        
        print(f"\n{'=' * 60}")
        print(f"  完成! 耗时 {elapsed:.1f}s")
        print(f"  探索 {result['pages_explored']} 页面, 生成 {result['test_case_count']} 用例")
        if exec_summary:
            print(f"  执行: {exec_summary.get('passed', 0)} PASS / "
                  f"{exec_summary.get('failed', 0)} FAIL / "
                  f"{exec_summary.get('healed_steps', 0)} healed")
        print(f"{'=' * 60}")
        
        return result
    
    def _run_exploration(self) -> KnowledgeGraph:
        """Phase 2: 执行递归探索"""
        strategy = self.current_strategy
        
        # 配置探索器
        explorer_config = ExplorerConfig(
            max_depth=strategy.max_depth,
            max_pages=strategy.max_pages,
            same_origin_only=strategy.same_origin_only,
        )
        
        # 初始化浏览器
        browser_config = BrowserConfig(
            headless=True,
            session_name=f"webui-{datetime.now().strftime('%H%M%S')}",
        )
        self.browser = AgentBrowser(browser_config)
        
        # 探索
        explorer = Explorer(browser=self.browser, config=explorer_config)
        graph = explorer.explore(strategy.target_url)
        
        # 保存知识图谱
        report_dir = self.config.get("report_dir", "reports")
        os.makedirs(report_dir, exist_ok=True)
        graph_path = os.path.join(report_dir, 
            f"knowledge_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        graph.save(graph_path)
        print(f"  知识图谱已保存: {graph_path}")
        
        # 清理浏览器
        self.browser.close()
        
        return graph
    
    def _run_planning(self) -> list:
        """Phase 3: 智能用例生成"""
        # 从配置读取规划参数
        planner_cfg = self.config.get("planner", {})
        config = PlannerConfig(
            cases_per_page=planner_cfg.get("cases_per_page", 10),
        )
        
        if "priority_distribution" in planner_cfg:
            config.priority_distribution = planner_cfg["priority_distribution"]
        
        # 生成用例
        self.planner = TestCasePlanner(config)
        cases = self.planner.plan(self.knowledge_graph)
        
        # 保存用例
        report_dir = self.config.get("report_dir", "reports")
        os.makedirs(report_dir, exist_ok=True)
        cases_path = os.path.join(report_dir,
            f"test_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        self.planner.save(cases, cases_path)
        
        return cases
    
    def _run_execution(self) -> list:
        """Phase 4: 自主执行测试用例"""
        if not self.test_cases:
            print("  无测试用例可执行")
            return []
        
        # 读取执行器配置
        exec_cfg = self.config.get("executor", {})
        config = ExecutionConfig(
            screenshot_on_step=exec_cfg.get("screenshot_on_step", True),
            screenshot_on_fail=exec_cfg.get("screenshot_on_fail", True),
            screenshot_dir=exec_cfg.get("screenshot_dir", "reports/screenshots"),
            max_retries_per_step=exec_cfg.get("max_retries_per_step", 2),
            step_timeout_ms=exec_cfg.get("step_timeout_ms", 30000),
            wait_after_action_ms=exec_cfg.get("wait_after_action_ms", 1000),
            verify_timeout_ms=exec_cfg.get("verify_timeout_ms", 5000),
            skip_on_first_failure=exec_cfg.get("skip_on_first_failure", False),
            continue_on_failure=exec_cfg.get("continue_on_failure", True),
            enable_healing=exec_cfg.get("enable_healing", True),
            verbose=exec_cfg.get("verbose", True),
        )
        
        # 初始化浏览器 (如果需要实际执行)
        browser = None
        if exec_cfg.get("use_browser", False):
            browser_config = BrowserConfig(
                headless=True,
                session_name=f"webui-exec-{datetime.now().strftime('%H%M%S')}",
            )
            browser = AgentBrowser(browser_config)
        
        # 创建执行器
        self.executor = TestExecutor(
            browser=browser,
            knowledge_graph=self.knowledge_graph,
            config=config,
        )
        
        # 执行所有用例
        results = self.executor.execute_all(self.test_cases, browser=browser)
        
        # 清理浏览器
        if browser:
            browser.close()
        
        # 保存执行结果
        report_dir = self.config.get("report_dir", "reports")
        os.makedirs(report_dir, exist_ok=True)
        results_path = os.path.join(report_dir,
            f"execution_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        self.reporter.export_json(results, os.path.basename(results_path))
        
        return results
    
    def _generate_report(self) -> str:
        """Phase 5: 生成综合报告"""
        graph = self.knowledge_graph
        strategy = self.current_strategy
        cases = self.test_cases
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 优先级统计
        from collections import defaultdict
        prio_count = defaultdict(int)
        cat_count = defaultdict(int)
        for c in cases:
            prio_count[c.priority] += 1
            cat_count[c.category] += 1
        
        report = f"""# AgentForWebUITest — 测试报告

**目标系统**: {strategy.target_url}
**测试模式**: {strategy.mode}
**生成时间**: {now}
**Agent版本**: v{self.VERSION} (Iteration {self.ITERATIONS})

## 探索统计

| 指标 | 数值 |
|------|------|
| 总页面数 | {graph.stats['total_pages']} |
| 总元素数 | {graph.stats['total_elements']} |
| 总表单数 | {graph.stats['total_forms']} |
| 总API端点 | {graph.stats['total_api_endpoints']} |
| 最大深度 | {graph.stats['max_depth_reached']} |

## 用例生成统计

| 指标 | 数值 |
|------|------|
| 总用例数 | {len(cases)} |
| P0 (核心) | {prio_count['P0']} |
| P1 (重要) | {prio_count['P1']} |
| P2 (边界) | {prio_count['P2']} |
| P3 (探索) | {prio_count['P3']} |

### 类别分布

| 类别 | 数量 |
|------|------|
| 表单测试 | {cat_count['form']} |
| 按钮测试 | {cat_count['button']} |
| 链接测试 | {cat_count['link']} |
| API测试 | {cat_count['api']} |
| 页面测试 | {cat_count['page']} |

"""

        # 执行结果汇总
        if self.executor and self.execution_results:
            exec_stats = self.executor.get_summary_stats()
            report += f"""## 执行结果

| 指标 | 数值 |
|------|------|
| 总用例数 | {exec_stats['total']} |
| ✅ 通过 | {exec_stats['passed']} |
| ❌ 失败 | {exec_stats['failed']} |
| ⚠️ 部分通过 | {exec_stats['partial']} |
| ⏭️ 跳过 | {exec_stats['skipped']} |
| **通过率** | **{exec_stats['pass_rate']}%** |
| 总步骤 | {exec_stats['total_steps']} |
| 通过步骤 | {exec_stats['passed_steps']} |
| 失败步骤 | {exec_stats['failed_steps']} |
| 🔧 愈合步骤 | {exec_stats['healed_steps']} |
| 总耗时 | {exec_stats['total_duration_ms']}ms |

"""
        
        # 发现的页面
        report += "## 发现的页面\n\n"
        for url, page in graph.pages.items():
            report += f"""### [{page.depth}] {page.title or url}
- URL: `{url}`
- 元素: {len(page.elements)} (按钮: {page.button_count}, 输入: {page.input_count})
- 链接: {len(page.child_links)}
- 表单: {len(page.forms)}
- API端点: {len(page.api_endpoints)}
"""
            if page.api_endpoints:
                report += "  - API调用:\n"
                for api in page.api_endpoints:
                    report += f"    - `{api.method} {api.url}` → {api.status}\n"
        
        # 列出精选用例 (P0和P1)
        report += f"""
## 精选用例 (P0/P1)

"""
        for c in cases:
            if c.priority in ("P0", "P1"):
                report += f"""### {c.id} [{c.priority}] {c.name}
- **类别**: {c.category}
- **来源**: {c.source_page}
- **描述**: {c.description}
- **步骤**:
"""
                for i, s in enumerate(c.steps, 1):
                    report += f"  {i}. {s.description or f'{s.action} → {s.target}'}\n"
                if c.expectations:
                    report += "- **预期**:\n"
                    for e in c.expectations:
                        report += f"  - {e.type} {e.operator} `{e.expected_value}`\n"
                report += "\n"
        
        report += f"""
---
**生成者**: AgentForWebUITest v{self.VERSION} (Iteration {self.ITERATIONS})
**用例文件**: reports/test_cases_*.json
**知识图谱**: reports/knowledge_graph_*.json
**执行结果**: reports/execution_results_*.json
"""
        
        # 保存报告
        report_dir = self.config.get("report_dir", "reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir,
            f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"  报告已保存: {report_path}")
        return report_path
    
    @staticmethod
    def _load_config(path: str = None) -> dict:
        """加载配置文件"""
        import yaml
        
        if path is None:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}
