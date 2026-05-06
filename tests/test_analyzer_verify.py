"""Verification script for analyzer.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import Analyzer, FailureAnalysis, TrendReport, BugReport
from src.analyzer import FailureCategory, TrendDirection


def test_analyzer_verify():
    """验证analyzer.py的所有数据类和序列化。"""
    print("All imports: OK")
    print(f"FailureCategory: {FailureCategory.ELEMENT_NOT_FOUND}, {FailureCategory.API_ERROR}")
    print(f"TrendDirection: {TrendDirection.IMPROVING}, {TrendDirection.STABLE}, {TrendDirection.DEGRADING}")

    # Test basic instantiation
    analyzer = Analyzer()
    print(f"Analyzer instance: OK")

    # Test FailureAnalysis
    fa = FailureAnalysis(
        root_cause_category=FailureCategory.ELEMENT_NOT_FOUND,
        details={"missing_element": "button.submit"},
        suggestions=["Try alternative selector"],
    )
    print(f"FailureAnalysis: {fa.root_cause_label}, confidence={fa.confidence}")

    # Test TrendReport
    tr = TrendReport(
        pass_rates_over_time=[("2024-01-01", 95.0), ("2024-01-02", 92.0)],
        regressions=["TC-001"],
        trend_direction=TrendDirection.DEGRADING,
    )
    print(f"TrendReport: {tr.trend_direction}, runs={tr.total_runs}")

    # Test BugReport
    br = BugReport(
        title="Test Bug",
        severity="MAJOR",
        test_case_id="TC-001",
        category="form",
        steps_to_reproduce=["1. Go to page", "2. Click button"],
        expected_behavior="Form submits",
        actual_behavior="Error 500",
    )
    print(f"BugReport: {br.bug_id}, {br.title}, severity={br.severity}")

    # Test to_dict serialization
    fa_dict = fa.to_dict()
    tr_dict = tr.to_dict()
    br_dict = br.to_dict()
    print(f"Serialization: FailureAnalysis keys={len(fa_dict)}, TrendReport keys={len(tr_dict)}, BugReport keys={len(br_dict)}")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_analyzer_verify()
