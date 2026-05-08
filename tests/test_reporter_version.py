#!/usr/bin/env python3
"""
Reporter 版本号自动校验 — CI 断言，防止升级时遗漏硬编码版本号。

校验三处:
  1. 源码级: reporter.py 无硬编码 v0.X 版本号
  2. 动态导入: reporter.version/iterations == WebUITestAgent.VERSION/ITERATIONS
  3. 输出一致性: Markdown / JSON / HTML 报告中版本号与 agent.py 一致

用法:
    pytest tests/test_reporter_version.py -v
    或:  make version-check
"""

import sys
import os
import json
import subprocess
from datetime import datetime

# 确保可以 import src 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.reporter import TestReporter
from src.agent import WebUITestAgent
from src.executor import TestExecutionResult, StepResult
from src.healer import HealingRecord


def test_reporter_no_hardcoded_version():
    """【CI断言 #1】reporter.py 源码中无硬编码版本号字符串 v0.X"""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reporter_path = os.path.join(repo_root, "src", "reporter.py")

    # grep for hardcoded version patterns like v0.5, v0.4, etc.
    result = subprocess.run(
        ["grep", "-n", r"v0\.[0-9]", reporter_path],
        capture_output=True, text=True,
    )

    # grep returns exit 1 when no matches found (that's what we want)
    matches = result.stdout.strip()
    assert result.returncode == 1, (
        f"❌ reporter.py 存在硬编码版本号 (grep exit={result.returncode}):\n"
        f"   请将以下行改为使用 {self.version} / {WebUITestAgent.VERSION} 动态引用:\n"
        f"   {matches}\n"
        f"   参考: reporter.py __init__ 中的动态导入模式"
    )


def test_reporter_dynamic_import():
    """【CI断言 #2】reporter 初始化的 version/iterations 与 agent.py 一致"""
    reporter = TestReporter(output_dir="reports")

    assert reporter.version == WebUITestAgent.VERSION, (
        f"❌ reporter.version={reporter.version} != agent.VERSION={WebUITestAgent.VERSION}\n"
        f"   请检查 reporter.__init__ 中的动态导入是否正确执行"
    )
    assert reporter.iterations == WebUITestAgent.ITERATIONS, (
        f"❌ reporter.iterations={reporter.iterations} != agent.ITERATIONS={WebUITestAgent.ITERATIONS}\n"
        f"   请检查 reporter.__init__ 中的动态导入是否正确执行"
    )


def _mock_results():
    """构造最小化的模拟执行结果，供报告生成测试使用"""
    step_pass = StepResult(
        action="navigate",
        target="https://httpbin.org",
        status="PASS",
        duration_ms=120,
        description="导航到目标页面",
        result_summary="页面加载成功",
        timestamp=datetime.now().isoformat(),
    )
    step_fail = StepResult(
        action="click",
        target="登录按钮",
        status="FAIL",
        duration_ms=80,
        description="点击登录按钮",
        error_message="元素不可见",
        timestamp=datetime.now().isoformat(),
    )
    result = TestExecutionResult(
        case_id="TC-001",
        case_title="登录功能测试",
        steps=[step_pass, step_fail],
        status="FAIL",
        total_duration_ms=200,
        category="form",
        priority="P0",
        healing_records=[
            HealingRecord(
                original_target="登录按钮",
                failed_selectors=["#login_btn"],
                successful_strategy="text_content",
                resolved_ref="@e3",
                confidence=0.95,
            )
        ],
    )
    return [result]


def test_reporter_markdown_contains_version():
    """【CI断言 #3a】生成的 Markdown 报告包含正确的版本号"""
    os.makedirs("reports", exist_ok=True)
    reporter = TestReporter(output_dir="reports")
    results = _mock_results()

    md_path = reporter.generate_summary(
        results,
        title="AgentForWebUITest — CI版本校验",
    )

    with open(md_path, 'r') as f:
        content = f.read()

    assert WebUITestAgent.VERSION in content, (
        f"❌ Markdown报告缺少版本号 (期望: {WebUITestAgent.VERSION})\n"
        f"   文件: {md_path}\n"
        f"   请检查 generate_summary() 中的 {self.version} 模板是否正确填充"
    )
    assert "Iteration" in content or WebUITestAgent.ITERATIONS in content, (
        f"❌ Markdown报告缺少迭代号 (期望: {WebUITestAgent.ITERATIONS})\n"
        f"   文件: {md_path}"
    )


def test_reporter_json_contains_version():
    """【CI断言 #3b】生成的 JSON 报告包含正确的版本号和迭代号"""
    os.makedirs("reports", exist_ok=True)
    reporter = TestReporter(output_dir="reports")
    results = _mock_results()

    json_path = reporter.export_json(results, "ci_version_check.json")

    with open(json_path, 'r') as f:
        jdata = json.load(f)

    assert jdata["agent_version"] == WebUITestAgent.VERSION, (
        f"❌ JSON agent_version={jdata['agent_version']} != {WebUITestAgent.VERSION}\n"
        f"   请检查 export_json() 中 'agent_version': self.version 是否正确"
    )
    assert jdata["iterations"] == WebUITestAgent.ITERATIONS, (
        f"❌ JSON iterations={jdata['iterations']} != {WebUITestAgent.ITERATIONS}\n"
        f"   请检查 export_json() 中 'iterations': self.iterations 是否正确"
    )


def test_reporter_html_contains_version():
    """【CI断言 #3c】生成的 HTML 报告包含正确的版本号"""
    os.makedirs("reports", exist_ok=True)
    reporter = TestReporter(output_dir="reports")
    results = _mock_results()

    html_path = reporter.generate_html(results)

    with open(html_path, 'r') as f:
        content = f.read()

    expected_version_str = f"v{WebUITestAgent.VERSION}"
    assert expected_version_str in content, (
        f"❌ HTML报告缺少版本号 (期望: {expected_version_str})\n"
        f"   文件: {html_path}\n"
        f"   请检查 generate_html() 中的 v{{self.version}} 模板是否正确填充"
    )


def test_reporter_timeline_html_contains_version():
    """【CI断言 #3d】生成的 Timeline HTML 包含正确的版本号"""
    os.makedirs("reports", exist_ok=True)
    reporter = TestReporter(output_dir="reports")
    results = _mock_results()

    timeline_path = reporter.generate_timeline(results)

    with open(timeline_path, 'r') as f:
        content = f.read()

    expected_version_str = f"v{WebUITestAgent.VERSION}"
    assert expected_version_str in content, (
        f"❌ Timeline HTML缺少版本号 (期望: {expected_version_str})\n"
        f"   文件: {timeline_path}\n"
        f"   请检查 generate_timeline() 中的 v{{self.version}} 模板是否正确填充"
    )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
