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
        self._screenshot_refs: Dict[int, str] = {}

    def generate_summary(self, results: List[TestExecutionResult],
                         knowledge_graph=None,
                         title: str = "AgentForWebUITest — 执行报告",
                         extra_info: Dict = None,
                         analyzer_results: Dict = None,
                         previous_run_data: Dict = None) -> str:
        """生成Markdown格式的测试报告

        Args:
            results: 执行结果列表
            knowledge_graph: 知识图谱（可选，用于附加上下文）
            title: 报告标题
            extra_info: 额外信息字典
            analyzer_results: 根因分析结果字典（可选）
            previous_run_data: 上次运行统计数据（可选，用于趋势对比）

        Returns:
            str: 报告文件路径
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        stats = self._compute_stats(results)
        healing_stats = self._compute_healing_stats(results)

        report = f"""# {title}

**生成时间**: {now}
**Agent版本**: v0.3.0 (Iteration 1+2+3+4)

---

## 🎯 执行摘要

| 指标 | 数值 |
|------|------|
| 总用例数 | {stats['total']} |
| **通过率** | **{stats['pass_rate']}%** |
| 总耗时 | {stats['total_duration_ms']:.0f}ms |
| 愈合成功率 | {healing_stats['success_rate']}% |
"""

        # Trend comparison
        if previous_run_data:
            prev_pass_rate = previous_run_data.get('pass_rate', 0)
            delta = round(stats['pass_rate'] - prev_pass_rate, 1)
            trend_icon = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
            report += f"| 上次通过率 | {prev_pass_rate}% |\n"
            report += f"| 趋势变化 | {trend_icon} {delta:+.1f}% |\n"

        report += f"""
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

                # Screenshot references for this test case
                if self._screenshot_refs:
                    tc_screenshots = {
                        idx: path
                        for idx, path in self._screenshot_refs.items()
                        if any(sr.step_index == idx for sr in result.step_results)
                    }
                    if tc_screenshots:
                        report += "#### 📸 步骤截图\n\n"
                        for idx in sorted(tc_screenshots):
                            ss_path = tc_screenshots[idx]
                            rel_path = os.path.relpath(ss_path, self.output_dir) if os.path.isabs(ss_path) else ss_path
                            report += f"- **步骤 {idx+1}**: ![步骤{idx+1}截图]({rel_path})\n"
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
        # Root cause analysis
        if analyzer_results:
            report += "## 🔍 根因分析\n\n"
            if analyzer_results.get("summary"):
                report += f"**分析摘要**: {analyzer_results['summary']}\n\n"
            root_causes = analyzer_results.get("root_causes", [])
            if root_causes:
                report += "| # | 根因类别 | 影响用例 | 建议 |\n"
                report += "|---|----------|----------|------|\n"
                for i, rc in enumerate(root_causes, 1):
                    cause = rc.get("cause", "未知")
                    affected = rc.get("affected_cases", "N/A")
                    suggestion = rc.get("suggestion", "待分析")
                    report += f"| {i} | {cause} | {affected} | {suggestion} |\n"
                report += "\n"
            patterns = analyzer_results.get("failure_patterns", [])
            if patterns:
                report += "### 重复失败模式\n\n"
                for pattern in patterns:
                    report += f"- **{pattern.get('pattern', '未知模式')}**: {pattern.get('count', 0)} 次\n"
                report += "\n"

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
            "iterations": "1+2+3+4",
            "summary": self._compute_stats(results),
            "healing_summary": self._compute_healing_stats(results),
            "results": [r.to_dict() for r in results],
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON结果已导出: {filepath}")
        return filepath

    def add_screenshot_references(self, screenshot_map: Dict[int, str]) -> None:
        """添加步骤截图引用映射

        截图将在Markdown和HTML报告中自动包含。

        Args:
            screenshot_map: 步骤索引到截图路径的映射字典
                           例如: {0: "screenshots/step1.png", 2: "screenshots/step3.png"}
        """
        self._screenshot_refs.update(screenshot_map)
        logger.info(f"已添加 {len(screenshot_map)} 个截图引用")

    def generate_html(self, results: List[TestExecutionResult],
                      output_path: str = None) -> str:
        """生成自包含HTML测试报告

        包含:
        - 内联CSS样式
        - 通过/失败颜色编码
        - 可折叠用例详情
        - 分步详情含耗时
        - 纯CSS饼图

        Args:
            results: 执行结果列表
            output_path: 输出路径（可选）

        Returns:
            str: HTML文件路径
        """
        if output_path is None:
            output_path = os.path.join(
                self.output_dir,
                f"execution_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        stats = self._compute_stats(results)
        healing_stats = self._compute_healing_stats(results)

        # Compute pie chart percentages
        total = stats['total']
        pct_pass = round(stats['passed'] / total * 100, 1) if total > 0 else 0
        pct_fail = round(stats['failed'] / total * 100, 1) if total > 0 else 0
        pct_partial = round(stats['partial'] / total * 100, 1) if total > 0 else 0
        pct_skip = round(stats['skipped'] / total * 100, 1) if total > 0 else 0

        # CSS conic-gradient pie — accumulate stops
        stops = []
        cumulative = 0.0
        for pct, color in [
            (pct_pass, "#4CAF50"),
            (pct_fail, "#F44336"),
            (pct_partial, "#FF9800"),
            (pct_skip, "#9E9E9E"),
        ]:
            if pct > 0:
                start = cumulative
                end = cumulative + pct
                stops.append(f"{color} {start:.1f}% {end:.1f}%")
                cumulative = end
        pie_gradient = ", ".join(stops) if stops else "#E0E0E0 0% 100%"

        # Status color helper
        def status_color(status):
            return {
                "PASS": "#4CAF50", "FAIL": "#F44336",
                "PARTIAL": "#FF9800", "SKIP": "#9E9E9E",
                "PENDING": "#607D8B",
            }.get(status, "#757575")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentForWebUITest — HTML 执行报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a237e, #283593); color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; opacity: 0.85; }}
.card {{ background: white; border-radius: 10px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card h2 {{ font-size: 18px; margin-bottom: 16px; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
.metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }}
.metric {{ background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }}
.metric .value {{ font-size: 28px; font-weight: bold; color: #1a237e; }}
.metric .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
.pie-section {{ display: flex; align-items: center; gap: 30px; flex-wrap: wrap; }}
.pie-chart {{ width: 180px; height: 180px; border-radius: 50%; background: conic-gradient({pie_gradient}); flex-shrink: 0; }}
.legend {{ display: flex; flex-direction: column; gap: 8px; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 14px; }}
.legend-dot {{ width: 14px; height: 14px; border-radius: 3px; }}
.status-badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: white; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
th {{ background: #f5f5f5; font-weight: 600; }}
details {{ margin-bottom: 12px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
details summary {{ padding: 14px 18px; cursor: pointer; font-weight: 600; font-size: 15px; background: #fafafa; user-select: none; display: flex; align-items: center; gap: 10px; }}
details summary:hover {{ background: #f0f0f0; }}
details[open] summary {{ border-bottom: 1px solid #e0e0e0; }}
.detail-body {{ padding: 18px; }}
.step-row {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
.step-row:last-child {{ border-bottom: none; }}
.step-time {{ font-family: monospace; color: #888; font-size: 12px; min-width: 55px; }}
.screenshot-img {{ max-width: 400px; border: 1px solid #ddd; border-radius: 6px; margin: 6px 0; }}
.screenshot-caption {{ font-size: 12px; color: #666; }}
.timeline {{ margin-top: 12px; }}
.timeline-bar-container {{ position: relative; height: 32px; background: #f0f0f0; border-radius: 4px; margin-bottom: 8px; }}
.timeline-bar {{ position: absolute; top: 4px; height: 24px; border-radius: 4px; display: flex; align-items: center; padding: 0 8px; font-size: 11px; color: white; font-weight: 600; white-space: nowrap; overflow: hidden; }}
.timeline-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: #999; margin-bottom: 4px; }}
.footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; padding: 16px; }}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
  <h1>🧪 AgentForWebUITest — 执行报告</h1>
  <div class="meta">生成时间: {now} &nbsp;|&nbsp; 版本: v0.3.0 (Iteration 1+2+3+4)</div>
</div>

<!-- 执行摘要 -->
<div class="card">
  <h2>🎯 执行摘要</h2>
  <div class="metrics-grid">
    <div class="metric"><div class="value">{stats['total']}</div><div class="label">总用例数</div></div>
    <div class="metric"><div class="value">{stats['pass_rate']}%</div><div class="label">通过率</div></div>
    <div class="metric"><div class="value">{stats['total_duration_ms']:.0f}ms</div><div class="label">总耗时</div></div>
    <div class="metric"><div class="value">{healing_stats['success_rate']}%</div><div class="label">愈合成功率</div></div>
  </div>
</div>

<!-- 饼图 + 统计 -->
<div class="card">
  <h2>📊 结果分布</h2>
  <div class="pie-section">
    <div class="pie-chart"></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#4CAF50"></div> ✅ 通过: {stats['passed']} ({pct_pass}%)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#F44336"></div> ❌ 失败: {stats['failed']} ({pct_fail}%)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#FF9800"></div> ⚠️ 部分通过: {stats['partial']} ({pct_partial}%)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#9E9E9E"></div> ⏭️ 跳过: {stats['skipped']} ({pct_skip}%)</div>
    </div>
  </div>
  <table style="margin-top:20px">
    <tr><th>指标</th><th>数值</th><th>指标</th><th>数值</th></tr>
    <tr><td>总步骤数</td><td>{stats['total_steps']}</td><td>通过步骤</td><td>{stats['passed_steps']}</td></tr>
    <tr><td>失败步骤</td><td>{stats['failed_steps']}</td><td>愈合步骤</td><td>{stats['healed_steps']}</td></tr>
  </table>
</div>

<!-- 用例详情 -->
<div class="card">
  <h2>📋 用例执行详情</h2>
"""

        for result in results:
            color = status_color(result.status)
            status_icon = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "SKIP": "⏭️", "PENDING": "⏳"}.get(result.status, "❓")
            html += f"""  <details>
    <summary>
      <span class="status-badge" style="background:{color}">{status_icon} {result.status}</span>
      {result.test_case_id} [{result.priority}] — {result.test_case_name}
      <span style="margin-left:auto;font-size:13px;color:#888">{result.total_duration_ms:.0f}ms</span>
    </summary>
    <div class="detail-body">
      <p><strong>类别:</strong> {result.category} &nbsp;|&nbsp; <strong>来源:</strong> <code>{result.source_page}</code> &nbsp;|&nbsp; <strong>通过率:</strong> {result.pass_rate}% ({result.passed_steps}/{result.total_steps})</p>
"""

            if result.error_summary:
                html += f'      <p style="color:#F44336"><strong>错误摘要:</strong> {result.error_summary}</p>\n'

            if result.step_results:
                html += '      <div style="margin-top:12px"><strong>步骤详情:</strong></div>\n'
                for sr in result.step_results:
                    sc = status_color(sr.status)
                    si = {"PASS": "✅", "FAIL": "❌", "HEALED": "🔧", "SKIP": "⏭️", "PENDING": "⏳"}.get(sr.status, "❓")
                    target = sr.step_target[:50] + "..." if len(sr.step_target) > 50 else sr.step_target
                    note = sr.error_message[:60] if sr.error_message else ""
                    html += f"""      <div class="step-row">
        <span class="status-badge" style="background:{sc};font-size:10px">{si}</span>
        <span style="font-weight:600">#{sr.step_index+1}</span>
        <span>{sr.step_action}</span>
        <code style="font-size:12px">{target}</code>
        <span class="step-time">{sr.duration_ms:.0f}ms</span>
        <span style="color:#F44336;font-size:12px">{note}</span>
      </div>
"""
                # Screenshot references in HTML
                if self._screenshot_refs:
                    tc_screenshots = {
                        idx: path
                        for idx, path in self._screenshot_refs.items()
                        if any(sr.step_index == idx for sr in result.step_results)
                    }
                    if tc_screenshots:
                        html += '      <div style="margin-top:10px"><strong>📸 步骤截图:</strong></div>\n'
                        for idx in sorted(tc_screenshots):
                            ss_path = tc_screenshots[idx]
                            rel_path = os.path.relpath(ss_path, self.output_dir) if os.path.isabs(ss_path) else ss_path
                            html += f'      <div style="margin:8px 0"><img class="screenshot-img" src="{rel_path}" alt="步骤{idx+1}截图"><br><span class="screenshot-caption">步骤 {idx+1} — {os.path.basename(ss_path)}</span></div>\n'

            if result.healing_records:
                html += '      <div style="margin-top:12px"><strong>🔧 愈合详情:</strong></div>\n'
                for hr in result.healing_records:
                    html += f"""      <div style="background:#fff8e1;padding:8px 12px;border-radius:6px;margin:6px 0;font-size:13px">
        <strong>目标:</strong> <code>{hr.original_target}</code><br>
        <strong>成功策略:</strong> {hr.successful_strategy} &nbsp;|&nbsp; <strong>置信度:</strong> {hr.confidence:.2f}
      </div>
"""

            html += "    </div>\n  </details>\n"

        html += "</div>\n"

        # Timeline section
        if results:
            html += self._build_html_timeline(results)

        html += """<div class="footer">
  <p>报告由 <strong>AgentForWebUITest v0.3.0</strong> 自动生成</p>
</div>
</div>
</body>
</html>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"HTML报告已保存: {output_path}")
        return output_path

    def _build_html_timeline(self, results: List[TestExecutionResult]) -> str:
        """构建HTML内嵌时间线（Gantt风格）"""
        if not results:
            return ""

        # Parse timestamps
        import datetime as _dt
        min_time = None
        max_time = None
        parsed = []
        for r in results:
            try:
                st = _dt.datetime.fromisoformat(r.start_time)
                et = _dt.datetime.fromisoformat(r.end_time)
            except (ValueError, TypeError):
                # Fallback: use duration only
                st = _dt.datetime(2000, 1, 1)
                et = st + _dt.timedelta(milliseconds=r.total_duration_ms)
            parsed.append((st, et, r))
            if min_time is None or st < min_time:
                min_time = st
            if max_time is None or et > max_time:
                max_time = et

        if min_time is None or max_time is None:
            return ""

        total_span = max(1, (max_time - min_time).total_seconds())
        start_ts = min_time.timestamp()

        def status_color(status):
            return {
                "PASS": "#4CAF50", "FAIL": "#F44336",
                "PARTIAL": "#FF9800", "SKIP": "#9E9E9E",
            }.get(status, "#757575")

        html = '<div class="card">\n  <h2>⏱️ 执行时间线</h2>\n  <div class="timeline">\n'

        for st, et, r in parsed:
            left_pct = (st.timestamp() - start_ts) / total_span * 100
            width_pct = max(1, (et.timestamp() - st.timestamp()) / total_span * 100)
            color = status_color(r.status)
            duration_s = (et - st).total_seconds()
            html += f"""    <div class="timeline-bar-container">
      <div class="timeline-bar" style="left:{left_pct:.2f}%;width:{width_pct:.2f}%;background:{color}">
        {r.test_case_id} — {duration_s:.1f}s
      </div>
    </div>
"""

        html += "  </div>\n</div>\n"
        return html

    def generate_timeline(self, results: List[TestExecutionResult],
                          output_path: str = None) -> str:
        """生成独立的时间线可视化HTML文件

        Gantt图风格，每个用例显示为水平条，按状态颜色编码。

        Args:
            results: 执行结果列表
            output_path: 输出路径（可选）

        Returns:
            str: 时间线HTML文件路径
        """
        if output_path is None:
            output_path = os.path.join(
                self.output_dir,
                f"timeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>执行时间线 — AgentForWebUITest</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a237e, #283593); color: white; padding: 24px 30px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 22px; }}
.header .meta {{ font-size: 13px; opacity: 0.8; margin-top: 4px; }}
.card {{ background: white; border-radius: 10px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.timeline {{ position: relative; padding-left: 180px; }}
.timeline-row {{ display: flex; align-items: center; margin-bottom: 10px; position: relative; }}
.timeline-label {{ position: absolute; left: -180px; width: 170px; text-align: right; font-size: 12px; color: #555; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; padding-right: 10px; }}
.timeline-track {{ flex: 1; position: relative; height: 36px; background: #f0f0f0; border-radius: 4px; }}
.timeline-bar {{ position: absolute; top: 6px; height: 24px; border-radius: 4px; min-width: 4px; display: flex; align-items: center; padding: 0 6px; font-size: 11px; color: white; font-weight: 600; white-space: nowrap; overflow: hidden; }}
.legend {{ display: flex; gap: 20px; margin-bottom: 20px; font-size: 13px; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}
.time-scale {{ display: flex; justify-content: space-between; font-size: 11px; color: #999; margin-left: 180px; margin-bottom: 6px; }}
.footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>⏱️ AgentForWebUITest — 执行时间线</h1>
  <div class="meta">生成时间: {now} &nbsp;|&nbsp; 版本: v0.3.0</div>
</div>
<div class="card">
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#4CAF50"></div> 通过</div>
    <div class="legend-item"><div class="legend-dot" style="background:#F44336"></div> 失败</div>
    <div class="legend-item"><div class="legend-dot" style="background:#FF9800"></div> 部分通过</div>
    <div class="legend-item"><div class="legend-dot" style="background:#9E9E9E"></div> 跳过</div>
  </div>
"""

        # Build timeline
        import datetime as _dt
        parsed = []
        min_time = None
        max_time = None
        for r in results:
            try:
                st = _dt.datetime.fromisoformat(r.start_time)
                et = _dt.datetime.fromisoformat(r.end_time)
            except (ValueError, TypeError):
                st = _dt.datetime(2000, 1, 1)
                et = st + _dt.timedelta(milliseconds=r.total_duration_ms)
            parsed.append((st, et, r))
            if min_time is None or st < min_time:
                min_time = st
            if max_time is None or et > max_time:
                max_time = et

        if min_time and max_time and parsed:
            total_span = max(1, (max_time - min_time).total_seconds())
            start_ts = min_time.timestamp()

            # Time scale
            html += '<div class="time-scale">\n'
            for i in range(6):
                pct = i * 20
                t = min_time + _dt.timedelta(seconds=total_span * pct / 100)
                html += f'  <span>{t.strftime("%H:%M:%S")}</span>\n'
            html += '</div>\n<div class="timeline">\n'

            def sc(status):
                return {"PASS": "#4CAF50", "FAIL": "#F44336", "PARTIAL": "#FF9800", "SKIP": "#9E9E9E"}.get(status, "#757575")

            for st, et, r in parsed:
                left_pct = (st.timestamp() - start_ts) / total_span * 100
                width_pct = max(1, (et.timestamp() - st.timestamp()) / total_span * 100)
                duration_s = (et - st).total_seconds()
                html += f"""  <div class="timeline-row">
    <span class="timeline-label">{r.test_case_id}</span>
    <div class="timeline-track">
      <div class="timeline-bar" style="left:{left_pct:.2f}%;width:{width_pct:.2f}%;background:{sc(r.status)}">
        {duration_s:.1f}s — {r.status}
      </div>
    </div>
  </div>
"""

            html += "</div>\n"

        html += """</div>
<div class="footer"><p>时间线由 <strong>AgentForWebUITest v0.3.0</strong> 生成</p></div>
</div>
</body>
</html>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"时间线已保存: {output_path}")
        return output_path

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
