#!/usr/bin/env python3
"""Quick verification script for judge.py"""
import sys
sys.path.insert(0, '/root/AgentForWebUITest')

from src.judge import Judge, JudgementResult, IndividualVerdict, OverallVerdict, CheckVerdict, CheckType, JudgeConfig, quick_judge
print('OK - All imports successful')

# Quick smoke test with mock data
from dataclasses import dataclass, field
from typing import List

@dataclass
class MockStepResult:
    step_index: int = 0
    step_action: str = "navigate"
    step_target: str = ""
    step_value: str = ""
    step_description: str = ""
    status: str = "PASS"
    duration_ms: float = 100.0
    error_message: str = ""
    screenshot_path: str = ""
    api_calls: List = field(default_factory=list)
    healing_record: object = None
    observe_snapshot: str = ""
    think_reasoning: str = ""
    act_detail: str = ""
    verify_result: str = ""
    timestamp: str = ""

@dataclass
class MockExecResult:
    test_case_id: str = "TC-TEST-001"
    test_case_name: str = "Test Case"
    priority: str = "P1"
    category: str = "page"
    source_page: str = "/test"
    status: str = "PASS"
    total_steps: int = 1
    passed_steps: int = 1
    failed_steps: int = 0
    healed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 100.0
    error_summary: str = ""
    step_results: List = field(default_factory=list)
    healing_records: List = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""

@dataclass
class MockExpectation:
    type: str = "page_content"
    target: str = ""
    expected_value: str = ""
    operator: str = "contains"

@dataclass
class MockTestCase:
    id: str = "TC-TEST-001"
    name: str = "Test Case"
    priority: str = "P1"
    category: str = "page"
    source_page: str = "/test"
    tags: List = field(default_factory=list)
    steps: List = field(default_factory=list)
    expectations: List = field(default_factory=list)
    description: str = ""
    generated_at: str = ""

# Test 1: Judge with mock data
sr = MockStepResult(
    step_index=0,
    step_action="navigate",
    step_target="/test",
    status="PASS",
    observe_snapshot="[button @e1] Click me [link @e2] Home [textbox @e3]",
    verify_result="✅ page_content contains /test",
    act_detail="navigate(/test)",
)

er = MockExecResult(
    test_case_id="TC-TEST-001",
    test_case_name="Smoke Test",
    step_results=[sr],
)

tc = MockTestCase(
    id="TC-TEST-001",
    name="Smoke Test",
    expectations=[
        MockExpectation(type="page_content", expected_value="Click me", operator="contains"),
        MockExpectation(type="url_contains", expected_value="/test", operator="contains"),
    ],
)

judge = Judge()
result = judge.judge(tc, er)  # type: ignore
print(f"Verdict: {result.overall_verdict}")
print(f"Confidence: {result.confidence:.3f}")
print(f"Checks: {result.pass_checks}/{result.total_checks} pass")
print(f"Recommendation: {result.recommendation}")

# Test 2: judge_all with multiple results
er2 = MockExecResult(
    test_case_id="TC-TEST-002",
    test_case_name="Failing Test",
    step_results=[
        MockStepResult(
            step_index=0,
            step_action="navigate",
            step_target="/fail",
            status="FAIL",
            error_message="element not interactable",
            observe_snapshot="[button @e1] Loading... spinner",
            verify_result="❌ page_content contains missing",
        )
    ],
    error_summary="element not interactable",
    failed_steps=1,
    passed_steps=0,
    total_steps=1,
)

tc2 = MockTestCase(
    id="TC-TEST-002",
    name="Failing Test",
    expectations=[
        MockExpectation(type="page_content", expected_value="missing", operator="contains"),
    ],
)

results = judge.judge_all([er, er2], [tc, tc2])  # type: ignore
print(f"\nTotal judged: {len(results)}")
for r in results:
    print(f"  {r.test_case_id}: {r.overall_verdict} (conf={r.confidence:.3f}, FP={r.false_positives_detected})")

summary = judge.get_summary()
print(f"\nSummary: {summary['total']} total, {summary['passed']} PASS, {summary['failed']} FAIL, {summary['flaky']} FLAKY")
print(f"Avg confidence: {summary['avg_confidence']}")

# Test 3: False positive filtering
error_sr = MockStepResult(
    step_index=0,
    step_action="click",
    step_target="button",
    status="FAIL",
    error_message="stale element reference: element is not attached to the page document",
    observe_snapshot="Loading... spinner progress",
    verify_result="❌ fail",
)
er3 = MockExecResult(
    test_case_id="TC-TEST-003",
    test_case_name="Flaky Test",
    step_results=[error_sr],
    error_summary="stale element reference: element is not attached to the page document",
    failed_steps=1,
    passed_steps=0,
    total_steps=1,
)
tc3 = MockTestCase(
    id="TC-TEST-003",
    name="Flaky Test",
    expectations=[],
)
result3 = judge.judge(tc3, er3)  # type: ignore
print(f"\nFlaky test verdict: {result3.overall_verdict}")
print(f"False positives: {result3.false_positives_detected}")
print(f"Recommendation: {result3.recommendation}")

print("\n✅ All smoke tests passed!")
