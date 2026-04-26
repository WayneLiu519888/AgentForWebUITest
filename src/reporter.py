"""
测试报告生成器 (Test Reporter) — 迭代3核心模块

从执行结果生成Markdown/JSON报告，包含:
  - 总览统计
  - 通过率
  - 失败详情
  - 愈合记录
  - 执行时间线

用法:
    from src.reporter import TestReporter
    reporter = TestReporter()
    reporter.generate_summary(results)  # → Markdown报告
    reporter.export_json(results, "reports/results.json")
"""

import os
import json
import logging
from dataclasses import asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict

try:
    from .executor import TestExecutionResult, StepResult
    from .healer import HealingRecord
except ImportError:
    from executor import TestExecutionResult, StepResult
    from healer import HealingRecord

logger = logging.getLogger(__name__)


class TestReporter:
    """测试报告生成器

    生成详细的Markdown测试报告和JSON导出。

    用法:
        reporter = TestReporter(output_dir="reports")
        md_path = reporter.generate_summary(results)
        json_path = reporter.export_json(results)
    """

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_summary(self, results: List[TestExecutionResult],
                         knowledge_graph=None,
                         title: str = "AgentForWebUITest — 执行报告",
                         extra_info: Dict = None) -> str:
        """生成Markdown格式的测试报告

        Args:
            results: 执行结果列表
            knowledge_graph: 知识图谱（可选，用于附加上下文）
            title: 报告标题
            extra_info: 额外信息字典

        Returns:
            str: 报告文件路径
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        stats = self._compute_stats(results)
        healing_stats = self._compute_healing_stats(results)

        report = f"""# {title}

**生成时间**: {now}
**Agent版本**: v0.3.0 (Iteration 1+2+3)

---

## 📊 执行概览

| 指标 | 数值 |
|------|------|
| 总用例数 | {stats['total']} |
| ✅ 通过 | {stats['passed']} |
| ❌ 失败 | {stats['failed']} |
| ⚠️ 部分通过 | {stats['partial']} |
| ⏭️ 跳过 | {stats['skipped']} |
| **通过率** | **{stats['pass_rate']}%** |
| 总步骤数 | {stats['total_steps']} |
| 通过步骤 | {stats['passed_steps']} |
| 失败步骤 | {stats['failed_steps']} |
| 愈合步骤 | {stats['healed_steps']} |
| 总耗时 | {stats['total_duration_ms']}ms |

## 🔧 自愈统计

| 指标 | 数值 |
|------|------|
| 愈合尝试 | {healing_stats['total_healings']} |
| 愈合成功 | {healing_stats['successful_healings']} |
| 愈合成功率 | {healing_stats['success_rate']}% |

"""

        if healing_stats.get("strategies"):
            report += "### 策略使用分布\n\n| 策略 | 成功次数 |\n|------|----------|\n"
            for strat, count in sorted(healing_stats["strategies"].items(),
                                       key=lambda x: -x[1]):
                report += f"| {strat} | {count} |\n"
            report += "\n"

        # 优先级分布
        report += "## 📈 优先级分布\n\n"
        report += "| 优先级 | 总数 | 通过 | 失败 | 通过率 |\n"
        report += "|--------|------|------|------|--------|\n"
        prio_stats = self._compute_priority_stats(results)
        for prio in ["P0", "P1", "P2", "P3"]:
            if prio in prio_stats:
                ps = prio_stats[prio]
                rate = round(ps['passed'] / ps['total'] * 100, 1) if ps['total'] > 0 else 0
                report += f"| {prio} | {ps['total']} | {ps['passed']} | {ps['failed']} | {rate}% |\n"
        report += "\n"

        # 类别分布
        report += "## 🏷️ 类别分布\n\n"
        report += "| 类别 | 总数 | 通过 | 失败 | 通过率 |\n"
        report += "|------|------|------|------|--------|\n"
        cat_stats = self._compute_category_stats(results)
        for cat in ["form", "button", "link", "api", "page"]:
            if cat in cat_stats:
                cs = cat_stats[cat]
                rate = round(cs['passed'] / cs['total'] * 100, 1) if cs['total'] > 0 else 0
                report += f"| {cat} | {cs['total']} | {cs['passed']} | {cs['failed']} | {rate}% |\n"
        report += "\n"

        # 详细结果
        report += "## 📋 用例执行详情\n\n"

        for result in results:
            status_icon = {
                "PASS": "✅",
                "FAIL": "❌",
                "PARTIAL": "⚠️",
                "SKIP": "⏭️",
                "PENDING": "⏳",
            }.get(result.status, "❓")

            report += f"### {status_icon} {result.test_case_id} [{result.priority}] {result.test_case_name}\n\n"
            report += f"- **状态**: {result.status}\n"
            report += f"- **类别**: {result.category}\n"
            report += f"- **来源页面**: `{result.source_page}`\n"
            report += f"- **通过率**: {result.pass_rate}% ({result.passed_steps}/{result.total_steps})\n"
            report += f"- **愈合步骤**: {result.healed_steps}\n"
            report += f"- **耗时**: {result.total_duration_ms:.0f}ms\n"

            if result.error_summary:
                report += f"- **错误摘要**: {result.error_summary}\n"

            report += "\n"

            # 步骤详情
            if result.step_results:
                report += "| # | 状态 | 操作 | 目标 | 耗时 | 备注 |\n"
                report += "|---|------|------|------|------|------|\n"
                for sr in result.step_results:
                    s_icon = {
                        "PASS": "✅", "FAIL": "❌", "HEALED": "🔧",
                        "SKIP": "⏭️", "PENDING": "⏳",
                    }.get(sr.status, "❓")
                    target = sr.step_target[:40] + "..." if len(sr.step_target) > 40 else sr.step_target
                    note = sr.error_message[:50] if sr.error_message else ""
                    report += (f"| {sr.step_index+1} | {s_icon} | {sr.step_action} | "
                              f"{target} | {sr.duration_ms:.0f}ms | {note} |\n")
                report += "\n"

            # 愈合记录
            if result.healing_records:
                report += "#### 🔧 愈合详情\n\n"
                for hr in result.healing_records:
                    report += f"- **目标**: `{hr.original_target}`\n"
                    report += f"  - 失败策略: {', '.join(hr.failed_selectors) if hr.failed_selectors else '无'}\n"
                    report += f"  - 成功策略: **{hr.successful_strategy}**\n"
                    report += f"  - 解析结果: {hr.resolved_ref} ({hr.resolved_description})\n"
                    report += f"  - 置信度: {hr.confidence:.2f}\n"
                report += "\n"

        # 失败详情汇总
        failed_results = [r for r in results if r.status in ("FAIL", "PARTIAL")]
        if failed_results:
            report += "## ❌ 失败详情\n\n"
            for fr in failed_results:
                report += f"### {fr.test_case_id}: {fr.test_case_name}\n\n"
                report += f"**错误**: {fr.error_summary}\n\n"
                failed_steps = [s for s in fr.step_results if s.status == "FAIL"]
                for fs in failed_steps:
                    report += f"- **步骤 {fs.step_index+1}**: `{fs.step_action} {fs.step_target}`\n"
                    report += f"  - 错误: {fs.error_message}\n"
                    if fs.act_detail:
                        report += f"  - 执行详情: {fs.act_detail[:200]}\n"
                report += "\n"

        # 执行时间线
        if results:
            report += "## ⏱️ 执行时间线\n\n"
            report += "| 时间 | 用例 | 状态 | 耗时 |\n"
            report += "|------|------|------|------|\n"
            for result in results:
                start = result.start_time[-12:] if len(result.start_time) > 12 else result.start_time
                end = result.end_time[-12:] if len(result.end_time) > 12 else result.end_time
                status_icon = {
                    "PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "SKIP": "⏭️",
                }.get(result.status, "❓")
                report += (f"| {start} → {end} | {result.test_case_id} | "
                          f"{status_icon} {result.status} | {result.total_duration_ms:.0f}ms |\n")
            report += "\n"

        # 附加上下文
        if extra_info:
            report += "## 📎 附加信息\n\n"
            for key, value in extra_info.items():
                report += f"- **{key}**: {value}\n"
            report += "\n"

        # 知识图谱摘要
        if knowledge_graph:
            stats = getattr(knowledge_graph, 'stats', {})
            report += "## 🗺️ 知识图谱摘要\n\n"
            report += f"- **总页面数**: {stats.get('total_pages', 'N/A')}\n"
            report += f"- **总元素数**: {stats.get('total_elements', 'N/A')}\n"
            report += f"- **总表单数**: {stats.get('total_forms', 'N/A')}\n"
            report += f"- **总API端点**: {stats.get('total_api_endpoints', 'N/A')}\n"
            report += "\n"

        report += "---\n\n"
        report += "*报告由 AgentForWebUITest v0.3.0 自动生成*\n"

        # 保存报告
        report_path = os.path.join(
            self.output_dir,
            f"execution_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"报告已保存: {report_path}")
        return report_path

    def export_json(self, results: List[TestExecutionResult],
                    filename: str = None) -> str:
        """导出JSON格式的测试结果

        Args:
            results: 执行结果列表
            filename: 输出文件名（可选）

        Returns:
            str: JSON文件路径
        """
        if filename is None:
            filename = f"execution_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(self.output_dir, filename)

        export_data = {
            "generated_at": datetime.now().isoformat(),
            "agent_version": "0.3.0",
            "iterations": "1+2+3",
            "summary": self._compute_stats(results),
            "healing_summary": self._compute_healing_stats(results),
            "results": [r.to_dict() for r in results],
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON结果已导出: {filepath}")
        return filepath

    # ── 统计计算 ──

    @staticmethod
    def _compute_stats(results: List[TestExecutionResult]) -> Dict:
        """计算综合统计"""
        total = len(results)
        if total == 0:
            return {
                "total": 0, "passed": 0, "failed": 0, "partial": 0, "skipped": 0,
                "pass_rate": 0.0, "total_steps": 0, "passed_steps": 0,
                "failed_steps": 0, "healed_steps": 0, "skipped_steps": 0,
                "total_duration_ms": 0,
            }

        return {
            "total": total,
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "partial": sum(1 for r in results if r.status == "PARTIAL"),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
            "pass_rate": round(
                sum(1 for r in results if r.status == "PASS") / total * 100, 1
            ),
            "total_steps": sum(r.total_steps for r in results),
            "passed_steps": sum(r.passed_steps for r in results),
            "failed_steps": sum(r.failed_steps for r in results),
            "healed_steps": sum(r.healed_steps for r in results),
            "skipped_steps": sum(r.skipped_steps for r in results),
            "total_duration_ms": round(sum(r.total_duration_ms for r in results), 0),
        }

    @staticmethod
    def _compute_healing_stats(results: List[TestExecutionResult]) -> Dict:
        """计算自愈统计"""
        all_healings = []
        for r in results:
            all_healings.extend(r.healing_records)

        total = len(all_healings)
        if total == 0:
            return {
                "total_healings": 0,
                "successful_healings": 0,
                "success_rate": 0.0,
                "strategies": {},
            }

        successful = sum(1 for h in all_healings if h.successful_strategy)
        strategy_counts = defaultdict(int)
        for h in all_healings:
            if h.successful_strategy:
                strategy_counts[h.successful_strategy] += 1

        return {
            "total_healings": total,
            "successful_healings": successful,
            "success_rate": round(successful / total * 100, 1) if total > 0 else 0.0,
            "strategies": dict(strategy_counts),
        }

    @staticmethod
    def _compute_priority_stats(results: List[TestExecutionResult]) -> Dict:
        """按优先级统计"""
        stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "partial": 0})
        for r in results:
            stats[r.priority]["total"] += 1
            if r.status == "PASS":
                stats[r.priority]["passed"] += 1
            elif r.status in ("FAIL", "PARTIAL"):
                stats[r.priority]["failed"] += 1
        return dict(stats)

    @staticmethod
    def _compute_category_stats(results: List[TestExecutionResult]) -> Dict:
        """按类别统计"""
        stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "partial": 0})
        for r in results:
            stats[r.category]["total"] += 1
            if r.status == "PASS":
                stats[r.category]["passed"] += 1
            elif r.status in ("FAIL", "PARTIAL"):
                stats[r.category]["failed"] += 1
        return dict(stats)
