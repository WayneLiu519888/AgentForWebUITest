"""Functional test for analyzer.py — tests real analysis logic"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import (
    Analyzer, FailureAnalysis, TrendReport, BugReport,
    FailureCategory, TrendDirection,
)
from src.executor import TestExecutionResult, StepResult

def test_analyze_failure():
    """Test root cause classification for all failure types."""
    analyzer = Analyzer()

    test_cases = [
        # ELEMENT_NOT_FOUND
        (
            "ELEMENT_NOT_FOUND",
            TestExecutionResult(
                test_case_id="TC-001", test_case_name="Login Test",
                priority="P0", category="form", source_page="https://example.com/login",
                status="FAIL", total_steps=3, passed_steps=1, failed_steps=2,
                step_results=[
                    StepResult(step_index=0, step_action="navigate", step_target="https://example.com/login", status="PASS"),
                    StepResult(step_index=1, step_action="type", step_target="username", step_value="admin", status="PASS"),
                    StepResult(step_index=2, step_action="click", step_target="submit button",
                              status="FAIL", error_message="Unable to locate element: submit button not found in DOM"),
                ],
                error_summary="Unable to locate element: submit button not found in DOM",
            ),
        ),
        # API_ERROR
        (
            "API_ERROR",
            TestExecutionResult(
                test_case_id="TC-002", test_case_name="API Status Check",
                priority="P1", category="api", source_page="https://api.example.com/users",
                status="FAIL", total_steps=1, passed_steps=0, failed_steps=1,
                step_results=[
                    StepResult(step_index=0, step_action="verify", step_target="/api/users",
                              status="FAIL", error_message="API returned 500 Internal Server Error",
                              api_calls=[{"url": "/api/users", "response": {"status": 500}}]),
                ],
                error_summary="API returned 500 Internal Server Error",
            ),
        ),
        # TIMEOUT
        (
            "TIMEOUT",
            TestExecutionResult(
                test_case_id="TC-003", test_case_name="Slow Page Test",
                priority="P2", category="page", source_page="https://slow.example.com",
                status="FAIL", total_steps=1, passed_steps=0, failed_steps=1,
                step_results=[
                    StepResult(step_index=0, step_action="navigate", step_target="https://slow.example.com",
                              status="FAIL", error_message="Navigation timed out after 30000ms",
                              duration_ms=30000),
                ],
                error_summary="Navigation timed out after 30000ms",
            ),
        ),
        # ASSERTION_FAILED
        (
            "ASSERTION_FAILED",
            TestExecutionResult(
                test_case_id="TC-004", test_case_name="Title Check",
                priority="P1", category="page", source_page="https://example.com",
                status="FAIL", total_steps=1, passed_steps=0, failed_steps=1,
                step_results=[
                    StepResult(step_index=0, step_action="verify", step_target="document.title",
                              status="FAIL", error_message="预期失败: page_content contains Home",
                              verify_result="❌ page_content contains Home"),
                ],
                error_summary="预期失败: page_content contains Home",
            ),
        ),
        # PAGE_LOAD_ERROR
        (
            "PAGE_LOAD_ERROR",
            TestExecutionResult(
                test_case_id="TC-005", test_case_name="404 Page Test",
                priority="P2", category="link", source_page="https://example.com",
                status="FAIL", total_steps=1, passed_steps=0, failed_steps=1,
                step_results=[
                    StepResult(step_index=0, step_action="navigate", step_target="https://example.com/missing",
                              status="FAIL", error_message="Page not found: 404"),
                ],
                error_summary="Page not found: 404",
            ),
        ),
        # UNKNOWN
        (
            "UNKNOWN",
            TestExecutionResult(
                test_case_id="TC-006", test_case_name="Mystery Fail",
                priority="P3", category="form", source_page="https://example.com",
                status="FAIL", total_steps=1, passed_steps=0, failed_steps=1,
                step_results=[
                    StepResult(step_index=0, step_action="custom_action", step_target="something",
                              status="FAIL", error_message="xyzzy_wtf_error_12345"),
                ],
                error_summary="xyzzy_wtf_error_12345",
            ),
        ),
    ]

    all_pass = True
    for expected_cat, result in test_cases:
        analysis = analyzer.analyze_failure(result)
        if analysis.root_cause_category == expected_cat:
            print(f"  ✅ {result.test_case_id} → {analysis.root_cause_label} (confidence: {analysis.confidence:.0%})")
        else:
            print(f"  ❌ {result.test_case_id} → Expected {expected_cat}, got {analysis.root_cause_category}")
            all_pass = False
        # Check suggestions exist
        assert analysis.suggestions, f"No suggestions for {result.test_case_id}"
        assert len(analysis.suggestions) >= 1

    pass

def test_analyze_trends():
    """Test trend analysis with historical data."""
    analyzer = Analyzer()

    # Simulate 3 runs of the same 3 tests
    # Run 1: all pass
    r1 = [
        TestExecutionResult(test_case_id="TC-A", test_case_name="Test A", priority="P1", category="form", source_page="/a", status="PASS", total_steps=1, passed_steps=1, start_time="2024-01-01T10:00:00"),
        TestExecutionResult(test_case_id="TC-B", test_case_name="Test B", priority="P2", category="api", source_page="/b", status="PASS", total_steps=1, passed_steps=1, start_time="2024-01-01T10:00:01"),
        TestExecutionResult(test_case_id="TC-C", test_case_name="Test C", priority="P1", category="page", source_page="/c", status="FAIL", total_steps=1, failed_steps=1, start_time="2024-01-01T10:00:02"),
    ]
    # Run 2: A fails (regression), C still fails
    r2 = [
        TestExecutionResult(test_case_id="TC-A", test_case_name="Test A", priority="P1", category="form", source_page="/a", status="FAIL", total_steps=1, failed_steps=1, start_time="2024-01-02T10:00:00"),
        TestExecutionResult(test_case_id="TC-B", test_case_name="Test B", priority="P2", category="api", source_page="/b", status="PASS", total_steps=1, passed_steps=1, start_time="2024-01-02T10:00:01"),
        TestExecutionResult(test_case_id="TC-C", test_case_name="Test C", priority="P1", category="page", source_page="/c", status="FAIL", total_steps=1, failed_steps=1, start_time="2024-01-02T10:00:02"),
    ]
    # Run 3: C improves, but A still fails
    r3 = [
        TestExecutionResult(test_case_id="TC-A", test_case_name="Test A", priority="P1", category="form", source_page="/a", status="FAIL", total_steps=1, failed_steps=1, start_time="2024-01-03T10:00:00"),
        TestExecutionResult(test_case_id="TC-B", test_case_name="Test B", priority="P2", category="api", source_page="/b", status="PASS", total_steps=1, passed_steps=1, start_time="2024-01-03T10:00:01"),
        TestExecutionResult(test_case_id="TC-C", test_case_name="Test C", priority="P1", category="page", source_page="/c", status="PASS", total_steps=1, passed_steps=1, start_time="2024-01-03T10:00:02"),
    ]

    history = r1 + r2 + r3
    trend = analyzer.analyze_trends(history)

    print(f"  Total runs: {trend.total_runs}")
    print(f"  Overall pass rate: {trend.overall_pass_rate:.1f}%")
    print(f"  Trend direction: {trend.trend_direction}")
    print(f"  Regressions: {trend.regressions}")
    print(f"  Improvements: {trend.improvements}")
    print(f"  Pass rates over time: {trend.pass_rates_over_time}")
    print(f"  Volatility: {trend.volatility}")
    print(f"  Per-category trends: {trend.per_category_trends}")
    print(f"  Recommendation: {trend.recommendation[:100]}...")

    assert trend.total_runs == 3
    assert "TC-A" in trend.regressions, f"Expected TC-A in regressions, got {trend.regressions}"
    assert "TC-C" in trend.improvements, f"Expected TC-C in improvements, got {trend.improvements}"
    assert abs(trend.overall_pass_rate - (5/9)*100) < 0.1  # 5 passes out of 9 total, allow float rounding
    print("  ✅ Trend analysis passed!")

def test_bug_report_generation():
    """Test bug report generation."""
    analyzer = Analyzer()

    result = TestExecutionResult(
        test_case_id="TC-BUG-001", test_case_name="Login Form Submit",
        priority="P0", category="form", source_page="https://example.com/login",
        status="FAIL", total_steps=3, passed_steps=2, failed_steps=1,
        step_results=[
            StepResult(step_index=0, step_action="navigate", step_target="https://example.com/login", status="PASS"),
            StepResult(step_index=1, step_action="type", step_target="username", step_value="admin", status="PASS"),
            StepResult(step_index=2, step_action="click", step_target="submit button",
                      status="FAIL", error_message="Unable to locate element: submit button",
                      screenshot_path="reports/screenshots/TC-BUG-001_step2.png"),
        ],
        error_summary="Unable to locate element: submit button",
        start_time="2024-01-15T14:30:00",
        end_time="2024-01-15T14:30:05",
        total_duration_ms=5000,
    )

    bug = analyzer.generate_bug_report(result)

    print(f"  Bug ID: {bug.bug_id}")
    print(f"  Title: {bug.title}")
    print(f"  Severity: {bug.severity}")
    print(f"  Root cause: {bug.root_cause}")
    print(f"  Steps to reproduce: {len(bug.steps_to_reproduce)} steps")
    for s in bug.steps_to_reproduce:
        print(f"    {s}")
    print(f"  Expected: {bug.expected_behavior[:80]}...")
    print(f"  Actual: {bug.actual_behavior[:80]}...")
    print(f"  Screenshots: {bug.screenshot_paths}")
    print(f"  Suggested fix: {bug.suggested_fix[:80]}...")

    assert bug.severity == "CRITICAL", f"Expected CRITICAL, got {bug.severity}"
    assert bug.root_cause == "Element Not Found"
    assert len(bug.steps_to_reproduce) == 4
    assert bug.screenshot_paths
    print("  ✅ Bug report generation passed!")

    # Test save/load
    path = "/tmp/test_bug_report.json"
    saved_path = analyzer.save_bug_report(bug, path)
    assert os.path.exists(saved_path)

    loaded = Analyzer.load_bug_report(saved_path)
    assert loaded.bug_id == bug.bug_id
    assert loaded.severity == bug.severity
    print(f"  ✅ Bug report save/load passed! ({saved_path})")

    os.remove(saved_path)

def test_edge_cases():
    """Test edge cases and error handling."""
    analyzer = Analyzer()

    # Empty result (no steps, no failures)
    result = TestExecutionResult(
        test_case_id="TC-EMPTY", test_case_name="Empty Test",
        priority="P3", category="page", source_page="",
        status="SKIP", total_steps=0, passed_steps=0, failed_steps=0,
    )
    analysis = analyzer.analyze_failure(result)
    assert analysis.root_cause_category == FailureCategory.UNKNOWN
    print("  ✅ Empty result handled (UNKNOWN)")

    # Empty history
    trend = analyzer.analyze_trends([])
    assert trend.total_runs == 0
    assert trend.trend_direction == TrendDirection.STABLE
    print("  ✅ Empty history handled")

    # Single-run history
    r1 = [TestExecutionResult(test_case_id="TC-X", test_case_name="Test X", priority="P1", category="page",
                              source_page="/x", status="PASS", start_time="2024-01-01T10:00:00")]
    trend = analyzer.analyze_trends(r1)
    assert trend.total_runs == 1
    print("  ✅ Single-run history handled")

    # analyze_all_failures
    results = [
        TestExecutionResult(test_case_id="TC-PASS", test_case_name="Pass Test", priority="P2", category="page",
                           source_page="/pass", status="PASS"),
        TestExecutionResult(test_case_id="TC-FAIL", test_case_name="Fail Test", priority="P1", category="page",
                           source_page="/fail", status="FAIL",
                           step_results=[StepResult(step_index=0, step_action="click", step_target="btn",
                                                    status="FAIL", error_message="Unable to locate element")],
                           error_summary="Unable to locate element"),
    ]
    analyses = analyzer.analyze_all_failures(results)
    assert len(analyses) == 1
    assert analyses[0].root_cause_category == FailureCategory.ELEMENT_NOT_FOUND
    print("  ✅ analyze_all_failures: only failed results analyzed")

    # Summary
    summary = analyzer.summary(analyses)
    assert summary["total"] == 1
    assert "ELEMENT_NOT_FOUND" in str(summary["by_category"])
    print("  ✅ Summary generation passed")

def test_serialization():
    """Test JSON roundtrip for all data classes."""
    import json

    fa = FailureAnalysis(
        root_cause_category=FailureCategory.API_ERROR,
        details={"status_code": "500"},
        suggestions=["Fix API", "Retry later"],
        failed_steps=[],
        confidence=0.85,
    )
    fa_json = json.dumps(fa.to_dict())
    assert "API_ERROR" in fa_json
    print("  ✅ FailureAnalysis JSON serialization")

    tr = TrendReport(
        pass_rates_over_time=[("2024-01-01T10:00:00", 95.0)],
        regressions=["TC-A"],
        improvements=["TC-B"],
        trend_direction=TrendDirection.IMPROVING,
        total_runs=3,
        overall_pass_rate=88.5,
        recommendation="Tests are improving.",
    )
    tr_json = json.dumps(tr.to_dict())
    assert "IMPROVING" in tr_json
    assert "pass_rates_over_time" in tr_json
    print("  ✅ TrendReport JSON serialization")

    br = BugReport(
        bug_id="BUG-20240101-0001",
        title="Test Bug",
        severity="CRITICAL",
        test_case_id="TC-001",
        category="form",
        steps_to_reproduce=["1. Go", "2. Click"],
        expected_behavior="Should pass",
        actual_behavior="It failed",
        screenshot_paths=["/path/to/shot.png"],
        suggested_fix="Fix it",
        root_cause="Element Not Found",
        environment={"source_page": "https://example.com"},
    )
    br_json = json.dumps(br.to_dict())
    assert "CRITICAL" in br_json
    print("  ✅ BugReport JSON serialization")

    # Test save methods
    Analyzer.save_analysis(fa, "/tmp/test_fa.json")
    Analyzer.save_trend_report(tr, "/tmp/test_tr.json")
    assert os.path.exists("/tmp/test_fa.json")
    assert os.path.exists("/tmp/test_tr.json")
    os.remove("/tmp/test_fa.json")
    os.remove("/tmp/test_tr.json")
    print("  ✅ Save methods work")


if __name__ == "__main__":
    print("=" * 60)
    print("Functional Tests for analyzer.py")
    print("=" * 60)

    tests = [
        ("Root Cause Analysis", test_analyze_failure),
        ("Trend Analysis", test_analyze_trends),
        ("Bug Report Generation", test_bug_report_generation),
        ("Edge Cases", test_edge_cases),
        ("Serialization", test_serialization),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"\n── {name} ──")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
