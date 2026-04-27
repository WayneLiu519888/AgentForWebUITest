"""
Root Cause Analyzer + Trend Analyzer + Bug Report Generator — v0.3.0

Core module for post-execution analysis:
  1. Root cause classification of test failures
  2. Trend analysis across historical runs
  3. Structured bug report generation

Usage:
    from src.analyzer import Analyzer, FailureAnalysis, TrendReport, BugReport

    analyzer = Analyzer()
    analysis = analyzer.analyze_failure(failed_result)
    trend = analyzer.analyze_trends(historical_results)
    bug = analyzer.generate_bug_report(execution_result, judgement_result)
    analyzer.save_bug_report(bug, "reports/bugs/bug-001.json")
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict, Counter

# ── Safe imports (handle missing dependencies) ──
try:
    from .executor import TestExecutionResult, StepResult
except ImportError:
    try:
        from executor import TestExecutionResult, StepResult
    except ImportError:
        # Define fallback types for standalone use
        @dataclass
        class TestExecutionResult:
            test_case_id: str = ""
            test_case_name: str = ""
            priority: str = ""
            category: str = ""
            source_page: str = ""
            status: str = "PENDING"
            total_steps: int = 0
            passed_steps: int = 0
            failed_steps: int = 0
            healed_steps: int = 0
            skipped_steps: int = 0
            total_duration_ms: float = 0.0
            error_summary: str = ""
            step_results: List = field(default_factory=list)
            healing_records: List = field(default_factory=list)
            start_time: str = ""
            end_time: str = ""

            @property
            def pass_rate(self) -> float:
                if self.total_steps == 0:
                    return 0.0
                return (self.passed_steps + self.healed_steps) / self.total_steps * 100

            def to_dict(self) -> Dict:
                d = asdict(self)
                d["pass_rate"] = round(self.pass_rate, 1)
                return d

        @dataclass
        class StepResult:
            step_index: int = 0
            step_action: str = ""
            step_target: str = ""
            step_value: str = ""
            step_description: str = ""
            status: str = "PENDING"
            duration_ms: float = 0.0
            error_message: str = ""
            screenshot_path: str = ""
            api_calls: List = field(default_factory=list)
            healing_record: Any = None
            observe_snapshot: str = ""
            think_reasoning: str = ""
            act_detail: str = ""
            verify_result: str = ""
            timestamp: str = ""

try:
    from .planner import TestCase, TestExpectation
except ImportError:
    try:
        from planner import TestCase, TestExpectation
    except ImportError:
        @dataclass
        class TestCase:
            id: str = ""
            name: str = ""
            priority: str = ""
            category: str = ""
            source_page: str = ""
            tags: List = field(default_factory=list)
            steps: List = field(default_factory=list)
            expectations: List = field(default_factory=list)
            description: str = ""
            generated_at: str = ""

        @dataclass
        class TestExpectation:
            type: str = ""
            target: str = ""
            expected_value: str = ""
            operator: str = "equals"

# ── JudgementResult: define our own since judge.py may not exist ──
try:
    from .judge import JudgementResult
except ImportError:
    try:
        from judge import JudgementResult
    except ImportError:
        @dataclass
        class JudgementResult:
            """Judgement result from the visual/layout judge (judge.py).

            This fallback is used when judge.py is not available yet.
            """
            test_case_id: str = ""
            verdict: str = ""  # PASS | FAIL | INCONCLUSIVE
            confidence: float = 0.0
            visual_score: float = 0.0
            layout_score: float = 0.0
            content_score: float = 0.0
            explanation: str = ""
            issues: List[str] = field(default_factory=list)
            suggestions: List[str] = field(default_factory=list)
            screenshot_paths: List[str] = field(default_factory=list)
            timestamp: str = ""

            def to_dict(self) -> Dict:
                return asdict(self)

            @staticmethod
            def from_dict(data: Dict) -> "JudgementResult":
                return JudgementResult(**{k: v for k, v in data.items()
                                          if k in JudgementResult.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
# Failure Classification Constants
# ═══════════════════════════════════════════════════════════════

class FailureCategory:
    """Root cause categories for test failures."""
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    PAGE_LOAD_ERROR = "PAGE_LOAD_ERROR"
    UNKNOWN = "UNKNOWN"

    # Human-readable labels
    LABELS = {
        ELEMENT_NOT_FOUND: "Element Not Found",
        API_ERROR: "API Error",
        TIMEOUT: "Timeout",
        ASSERTION_FAILED: "Assertion Failed",
        PAGE_LOAD_ERROR: "Page Load Error",
        UNKNOWN: "Unknown",
    }

    @classmethod
    def label(cls, category: str) -> str:
        return cls.LABELS.get(category, category)


class TrendDirection:
    """Trend direction indicators."""
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class FailureAnalysis:
    """Root cause analysis of a single test failure.

    Attributes:
        root_cause_category: One of FailureCategory constants
        root_cause_label: Human-readable label
        details: Specific details about the failure
        suggestions: List of actionable fix suggestions
        failed_steps: The step results that actually failed
        contributing_factors: Secondary factors that may have contributed
        confidence: How confident the classifier is (0.0-1.0)
        analyzed_at: ISO timestamp of when analysis was performed
    """
    root_cause_category: str = FailureCategory.UNKNOWN
    root_cause_label: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    failed_steps: List[StepResult] = field(default_factory=list)
    contributing_factors: List[str] = field(default_factory=list)
    confidence: float = 0.0
    analyzed_at: str = ""

    def __post_init__(self):
        if not self.root_cause_label:
            self.root_cause_label = FailureCategory.label(self.root_cause_category)
        if not self.analyzed_at:
            self.analyzed_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["failed_steps"] = [
            {
                "step_index": s.step_index,
                "step_action": s.step_action,
                "step_target": s.step_target,
                "step_value": s.step_value,
                "step_description": s.step_description,
                "status": s.status,
                "error_message": s.error_message,
                "screenshot_path": s.screenshot_path,
            }
            for s in self.failed_steps
        ]
        return d


@dataclass
class TrendReport:
    """Trend analysis across multiple test runs.

    Attributes:
        pass_rates_over_time: List of (timestamp, pass_rate_pct) tuples
        regressions: List of test_case_ids that went from pass to fail
        improvements: List of test_case_ids that went from fail to pass
        trend_direction: IMPROVING | STABLE | DEGRADING
        total_runs: Number of runs analyzed
        overall_pass_rate: Average pass rate across all runs
        volatility: Standard deviation of pass rates (high = unstable)
        per_category_trends: Breakdown by test category
        recommendation: Actionable recommendation based on trend
    """
    pass_rates_over_time: List[Tuple[str, float]] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    trend_direction: str = TrendDirection.STABLE
    total_runs: int = 0
    overall_pass_rate: float = 0.0
    volatility: float = 0.0
    per_category_trends: Dict[str, Dict] = field(default_factory=dict)
    recommendation: str = ""
    analyzed_at: str = ""

    def __post_init__(self):
        if not self.analyzed_at:
            self.analyzed_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        d = asdict(self)
        # Convert tuples to list of dicts for JSON serialization
        d["pass_rates_over_time"] = [
            {"timestamp": ts, "pass_rate": pr}
            for ts, pr in self.pass_rates_over_time
        ]
        return d


@dataclass
class BugReport:
    """Structured bug report generated from failed test + judgement.

    Attributes:
        bug_id: Unique bug identifier
        title: Concise bug title
        severity: CRITICAL | MAJOR | MINOR
        test_case_id: Associated test case
        category: Test category
        status: NEW | CONFIRMED | IN_PROGRESS | RESOLVED
        steps_to_reproduce: Numbered list of reproduction steps
        expected_behavior: What was expected
        actual_behavior: What actually happened
        screenshot_paths: List of screenshot file paths
        suggested_fix: Actionable fix recommendation
        root_cause: Failure category from analysis
        judgement_summary: Key findings from visual judgement
        environment: Environment info (source page, timestamp, etc.)
        reported_at: ISO timestamp
    """
    bug_id: str = ""
    title: str = ""
    severity: str = "MINOR"  # CRITICAL | MAJOR | MINOR
    test_case_id: str = ""
    category: str = ""
    status: str = "NEW"

    steps_to_reproduce: List[str] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    screenshot_paths: List[str] = field(default_factory=list)
    suggested_fix: str = ""
    root_cause: str = ""
    judgement_summary: str = ""

    environment: Dict[str, str] = field(default_factory=dict)
    reported_at: str = ""

    def __post_init__(self):
        if not self.reported_at:
            self.reported_at = datetime.now().isoformat()
        if not self.bug_id:
            self.bug_id = self._generate_bug_id()

    def _generate_bug_id(self) -> str:
        """Generate a unique bug ID: BUG-YYYYMMDD-XXXX"""
        date_part = datetime.now().strftime("%Y%m%d")
        hash_part = hex(hash(self.test_case_id + self.title + self.reported_at) & 0xFFFF)[2:].upper().zfill(4)
        return f"BUG-{date_part}-{hash_part}"

    def to_dict(self) -> Dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# Analyzer
# ═══════════════════════════════════════════════════════════════

class Analyzer:
    """Root Cause Analyzer + Trend Analyzer + Bug Report Generator.

    Usage:
        analyzer = Analyzer()

        # Root cause analysis
        analysis = analyzer.analyze_failure(failed_result)
        print(f"Root cause: {analysis.root_cause_label}")
        for s in analysis.suggestions:
            print(f"  → {s}")

        # Trend analysis
        trend = analyzer.analyze_trends(historical_results)
        print(f"Trend: {trend.trend_direction} (pass rate: {trend.overall_pass_rate:.1f}%)")

        # Bug report
        bug = analyzer.generate_bug_report(failed_result, judgement)
        analyzer.save_bug_report(bug, "reports/bugs/bug-001.json")
    """

    def __init__(self):
        self._bug_counter = 0

    # ─────────────────────────────────────────────────────────
    # 1. Root Cause Analysis
    # ─────────────────────────────────────────────────────────

    def analyze_failure(self, result: TestExecutionResult) -> FailureAnalysis:
        """Analyze a failed TestExecutionResult to determine root cause.

        Args:
            result: A TestExecutionResult with status FAIL or PARTIAL.

        Returns:
            FailureAnalysis with root cause classification, details, and suggestions.
        """
        if not isinstance(result, TestExecutionResult):
            raise TypeError(f"Expected TestExecutionResult, got {type(result).__name__}")

        # Extract all failed steps
        failed_steps = [s for s in result.step_results if s.status == "FAIL"]
        if not failed_steps:
            # No explicit failures — check for partial/skip or error_summary
            if result.error_summary:
                failed_steps = result.step_results  # Analyze all steps
            else:
                # No failure data to analyze
                return FailureAnalysis(
                    root_cause_category=FailureCategory.UNKNOWN,
                    details={"reason": "No failed steps found in result"},
                    suggestions=["Review test execution logs for anomalies"],
                    failed_steps=[],
                    confidence=0.0,
                )

        # Classify each failed step, then pick the dominant category
        classifications = []
        for step in failed_steps:
            cat, detail, confidence = self._classify_step_failure(step, result)
            classifications.append((cat, detail, confidence, step))

        # Aggregate: use the highest-confidence classification
        classifications.sort(key=lambda x: x[2], reverse=True)
        primary_cat, primary_detail, primary_conf, primary_step = classifications[0]

        # Merge details from all classifications
        merged_details = dict(primary_detail) if primary_detail else {}
        merged_details["total_failed_steps"] = len(failed_steps)
        merged_details["total_steps"] = result.total_steps
        merged_details["test_case_id"] = result.test_case_id
        merged_details["test_case_name"] = result.test_case_name
        merged_details["source_page"] = result.source_page

        # Identify contributing factors (secondary categories)
        contributing = []
        seen_cats = {primary_cat}
        for cat, detail, conf, step in classifications[1:]:
            if cat not in seen_cats and conf > 0.3:
                contributing.append(f"{FailureCategory.label(cat)} (confidence: {conf:.0%})")
                seen_cats.add(cat)

        # Generate suggestions
        suggestions = self._generate_suggestions(primary_cat, merged_details, failed_steps)

        return FailureAnalysis(
            root_cause_category=primary_cat,
            details=merged_details,
            suggestions=suggestions,
            failed_steps=failed_steps,
            contributing_factors=contributing,
            confidence=primary_conf,
        )

    def _classify_step_failure(self, step: StepResult,
                                result: TestExecutionResult) -> Tuple[str, Dict, float]:
        """Classify a single failed step into a root cause category.

        Returns:
            Tuple of (category, details_dict, confidence)
        """
        error_msg = (step.error_message or "").lower()
        target = step.step_target or ""
        action = step.step_action or ""
        description = (step.step_description or "").lower()

        # ── Pattern matching for failure classification ──

        # 1. ELEMENT_NOT_FOUND
        element_not_found_patterns = [
            "unable to locate element", "cannot find element",
            "element not found", "no such element",
            "无法定位元素", "找不到元素", "element not interactable",
            "stale element reference", "selector not found",
            "no element matching", "could not find",
            "element is not visible", "element is not attached",
        ]
        for pat in element_not_found_patterns:
            if pat in error_msg or pat in description:
                element_info = {
                    "missing_element": target,
                    "action_attempted": action,
                    "step_description": step.step_description,
                    "original_error": step.error_message,
                }
                # Try to extract selector from error
                if "selector" in error_msg:
                    import re
                    m = re.search(r'selector[:\s]+["\']?([^"\')\n]+)', error_msg)
                    if m:
                        element_info["selector"] = m.group(1).strip()
                return (
                    FailureCategory.ELEMENT_NOT_FOUND,
                    element_info,
                    0.85 if "unable to locate" in error_msg else 0.75,
                )

        # 2. PAGE_LOAD_ERROR (check before API_ERROR — page-specific patterns)
        page_load_patterns = [
            "page not found", "404",
            "navigation failed", "cannot load page",
            "page load", "connection refused",
            "dns", "unreachable", "ssl error",
            "certificate", "redirect loop",
        ]
        for pat in page_load_patterns:
            if pat in error_msg:
                page_info = {
                    "error_type": pat,
                    "target_url": target or result.source_page,
                    "original_error": step.error_message,
                }
                return (
                    FailureCategory.PAGE_LOAD_ERROR,
                    page_info,
                    0.70 if "404" in error_msg else 0.65,
                )

        # 3. API_ERROR (check after PAGE_LOAD_ERROR to avoid misclassifying 404 pages)
        api_error_patterns = [
            "api returned", "status code", "4xx", "5xx",
            "bad request", "unauthorized", "forbidden",
            "internal server error",
            "service unavailable", "gateway timeout",
            "api error", "network error", "fetch failed",
            "response status", "http error",
        ]
        for pat in api_error_patterns:
            if pat in error_msg:
                api_info = {
                    "error_type": pat,
                    "action_attempted": action,
                    "target": target,
                    "original_error": step.error_message,
                }
                # Check step's api_calls for more detail
                if step.api_calls:
                    api_info["api_calls"] = step.api_calls

                # Extract status code if present
                import re
                m = re.search(r'(\d{3})\s', error_msg)
                if m:
                    api_info["status_code"] = m.group(1)

                return (
                    FailureCategory.API_ERROR,
                    api_info,
                    0.80,
                )

        # 4. TIMEOUT
        timeout_patterns = [
            "timeout", "timed out", "time limit exceeded",
            "took too long", "wait exceeded", "maximum wait",
            "page load timeout", "script timeout",
        ]
        for pat in timeout_patterns:
            if pat in error_msg:
                timeout_info = {
                    "timeout_type": pat,
                    "action_attempted": action,
                    "target": target,
                    "step_duration_ms": step.duration_ms,
                    "original_error": step.error_message,
                }
                return (
                    FailureCategory.TIMEOUT,
                    timeout_info,
                    0.80,
                )

        # 5. ASSERTION_FAILED
        assertion_patterns = [
            "expected", "assertion failed", "assert",
            "预期失败", "期望", "expected value",
            "expected_value", "mismatch", "did not match",
            "should be", "should have",
        ]
        for pat in assertion_patterns:
            if pat in error_msg:
                assertion_info = {
                    "assertion_type": pat,
                    "target": target,
                    "original_error": step.error_message,
                }
                # Try to extract expected vs actual from verify_result
                verify = (step.verify_result or "").lower()
                if "✅" in verify or "❌" in verify:
                    assertion_info["verify_details"] = step.verify_result

                return (
                    FailureCategory.ASSERTION_FAILED,
                    assertion_info,
                    0.75,
                )

        # 6. Heuristic: failed verify → ASSERTION_FAILED
        verify = (step.verify_result or "").lower()
        if "❌" in verify or "预期失败" in verify or "expected" in verify:
            return (
                FailureCategory.ASSERTION_FAILED,
                {"verify_details": step.verify_result, "original_error": step.error_message},
                0.60,
            )

        # 7. Heuristic: failed navigate → PAGE_LOAD_ERROR
        if action == "navigate":
            return (
                FailureCategory.PAGE_LOAD_ERROR,
                {"target_url": target, "original_error": step.error_message},
                0.55,
            )

        # 8. Heuristic: failed verify → ASSERTION_FAILED
        if action == "verify":
            return (
                FailureCategory.ASSERTION_FAILED,
                {"target": target, "original_error": step.error_message},
                0.55,
            )

        # 9. Fallback: UNKNOWN
        return (
            FailureCategory.UNKNOWN,
            {
                "error_message": step.error_message,
                "action": action,
                "target": target,
                "reason": "No matching pattern found",
            },
            0.30,
        )

    def _generate_suggestions(self, category: str, details: Dict,
                               failed_steps: List[StepResult]) -> List[str]:
        """Generate actionable fix suggestions based on root cause category.

        Args:
            category: FailureCategory constant
            details: Aggregated failure details
            failed_steps: List of failed StepResults

        Returns:
            List of actionable suggestion strings
        """
        suggestions = []

        if category == FailureCategory.ELEMENT_NOT_FOUND:
            element = details.get("missing_element", "unknown element")
            suggestions.append(
                f"🔍 Element '{element}' was not found in the DOM. "
                "Try using an alternative selector (e.g., by text, aria-label, or test-id)."
            )
            suggestions.append(
                f"📄 Check if the page structure has changed — the target element "
                "may have been renamed, removed, or dynamically loaded."
            )
            suggestions.append(
                "⏱️ Add an explicit wait before interacting with this element "
                "(e.g., wait for it to become visible, or wait for network idle)."
            )
            suggestions.append(
                "🔧 Consider registering this selector in the SelectorHealer "
                "for automatic healing on future runs."
            )
            if any(s.step_action == "click" for s in failed_steps):
                suggestions.append(
                    "🖱️ For click failures, verify the element is within the viewport "
                    "and not obscured by modals, overlays, or cookie banners."
                )

        elif category == FailureCategory.API_ERROR:
            status = details.get("status_code", "unknown")
            suggestions.append(
                f"🌐 API returned error (status: {status}). "
                "Check the API documentation for correct parameters and authentication requirements."
            )
            suggestions.append(
                "🔄 Retry the request with different parameters — the API may "
                "have rate limits or the endpoint may have changed."
            )
            suggestions.append(
                "📊 Review the network tab / API logs to confirm the actual "
                "request payload and response body."
            )
            if status and status.startswith("4"):
                suggestions.append(
                    "🔑 4xx errors often indicate authentication issues — "
                    "verify tokens, cookies, and request headers."
                )
            elif status and status.startswith("5"):
                suggestions.append(
                    "🛠️ 5xx errors indicate server-side issues — "
                    "check service health and retry after a delay."
                )

        elif category == FailureCategory.TIMEOUT:
            suggestions.append(
                "⏰ Increase the step timeout or wait duration — "
                "the operation took longer than the current limit."
            )
            suggestions.append(
                "🌐 Check network conditions — slow responses may indicate "
                "bandwidth issues or server-side performance problems."
            )
            suggestions.append(
                "📄 For navigation timeouts, verify the target URL is "
                "reachable and the page isn't stuck in a redirect loop."
            )
            suggestions.append(
                "⚡ Consider breaking the test into smaller steps with "
                "intermediate waits to isolate the slow operation."
            )

        elif category == FailureCategory.ASSERTION_FAILED:
            suggestions.append(
                "✔️ Review the expected value — the assertion may be outdated "
                "if the application behavior has changed."
            )
            suggestions.append(
                "📋 Compare expected vs actual values in the test logs "
                "to understand the nature of the mismatch."
            )
            suggestions.append(
                "🔧 Update the test expectation or the test data to match "
                "the current application state."
            )
            suggestions.append(
                "📸 Check the step screenshot to visually confirm what the "
                "page actually displayed at the time of failure."
            )

        elif category == FailureCategory.PAGE_LOAD_ERROR:
            target = details.get("target_url", "the page")
            suggestions.append(
                f"🌍 Navigation to '{target}' failed. "
                "Verify the URL is correct and the page is accessible."
            )
            suggestions.append(
                "🔗 Check for SSL certificate issues, DNS resolution problems, "
                "or network connectivity."
            )
            suggestions.append(
                "📄 The page may have moved — check for 301/302 redirects "
                "and update the test URL accordingly."
            )
            suggestions.append(
                "🔄 Add retry logic for transient network failures "
                "(consider using a retry decorator or exponential backoff)."
            )

        elif category == FailureCategory.UNKNOWN:
            suggestions.append(
                "🔍 The failure could not be automatically classified. "
                "Review the full error message and step logs manually."
            )
            suggestions.append(
                "📸 Examine the failure screenshot to understand what "
                "the page state was at the time of the error."
            )
            if failed_steps:
                err_msgs = set(s.error_message for s in failed_steps if s.error_message)
                for msg in list(err_msgs)[:2]:
                    suggestions.append(f"📝 Raw error: {msg[:120]}")

        return suggestions

    # ─────────────────────────────────────────────────────────
    # 2. Trend Analysis
    # ─────────────────────────────────────────────────────────

    def analyze_trends(self, history: List[TestExecutionResult]) -> TrendReport:
        """Analyze historical test execution results for trends.

        Detects regressions (previously passing tests that now fail),
        improvements (previously failing tests that now pass),
        and overall trend direction.

        Args:
            history: List of TestExecutionResult from multiple runs.
                     Each run may contain results for many test cases.

        Returns:
            TrendReport with pass rates, regressions, improvements, and direction.
        """
        if not history:
            return TrendReport(
                total_runs=0,
                overall_pass_rate=0.0,
                trend_direction=TrendDirection.STABLE,
                recommendation="No historical data available for trend analysis.",
            )

        # Group results by test_case_id to track per-test history
        # We also track the chronological order of runs
        test_history: Dict[str, List[TestExecutionResult]] = defaultdict(list)

        # Determine run groups (results sharing the same start_time ≈ same run)
        run_groups = self._group_by_run(history)

        # Build per-test-case timeline
        for result in history:
            test_history[result.test_case_id].append(result)

        # Compute pass rates per run
        pass_rates_over_time = []
        for run_ts, run_results in run_groups:
            if run_results:
                passed = sum(1 for r in run_results if r.status == "PASS" or r.status == "HEALED")
                rate = (passed / len(run_results)) * 100
                pass_rates_over_time.append((run_ts, round(rate, 1)))

        # Sort by timestamp
        pass_rates_over_time.sort(key=lambda x: x[0])

        # Detect regressions and improvements (comparing earliest vs latest status)
        regressions = []
        improvements = []

        for tc_id, results in test_history.items():
            if len(results) < 2:
                continue

            # Sort by start_time
            results.sort(key=lambda r: r.start_time or "")

            # Get earliest and latest status
            earliest = results[0]
            latest = results[-1]

            earliest_passing = earliest.status in ("PASS",)
            latest_passing = latest.status in ("PASS",)

            if earliest_passing and not latest_passing:
                regressions.append(tc_id)
            elif not earliest_passing and latest_passing:
                improvements.append(tc_id)

        # Compute trend direction
        trend_direction = self._compute_trend_direction(
            pass_rates_over_time, regressions, improvements
        )

        # Compute overall pass rate
        if history:
            passed_total = sum(
                1 for r in history if r.status in ("PASS",)
            )
            overall_pass_rate = round((passed_total / len(history)) * 100, 1)
        else:
            overall_pass_rate = 0.0

        # Compute volatility (stddev of pass rates across runs)
        volatility = self._compute_volatility(pass_rates_over_time)

        # Per-category trends
        per_category = self._compute_category_trends(history)

        # Generate recommendation
        recommendation = self._generate_trend_recommendation(
            trend_direction, regressions, improvements, overall_pass_rate, volatility
        )

        return TrendReport(
            pass_rates_over_time=pass_rates_over_time,
            regressions=regressions,
            improvements=improvements,
            trend_direction=trend_direction,
            total_runs=len(run_groups),
            overall_pass_rate=overall_pass_rate,
            volatility=volatility,
            per_category_trends=per_category,
            recommendation=recommendation,
        )

    def _group_by_run(self, history: List[TestExecutionResult]
                      ) -> List[Tuple[str, List[TestExecutionResult]]]:
        """Group results by their run (using start_time proximity).

        Results within 60 seconds of each other are considered the same run.
        """
        if not history:
            return []

        # Sort by start_time
        sorted_results = sorted(history, key=lambda r: r.start_time or "")
        groups = []
        current_group = []
        current_ts = None

        for r in sorted_results:
            st = r.start_time or ""
            if current_ts is None:
                current_ts = st
                current_group = [r]
            else:
                # Check if within 60 seconds of the group start
                try:
                    t1 = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(st.replace("Z", "+00:00"))
                    if abs((t2 - t1).total_seconds()) <= 60:
                        current_group.append(r)
                    else:
                        groups.append((current_ts, current_group))
                        current_ts = st
                        current_group = [r]
                except (ValueError, TypeError):
                    # If timestamps can't be parsed, treat each as separate run
                    groups.append((current_ts, current_group))
                    current_ts = st
                    current_group = [r]

        if current_group:
            groups.append((current_ts, current_group))

        return groups

    def _compute_trend_direction(self, pass_rates: List[Tuple[str, float]],
                                  regressions: List[str],
                                  improvements: List[str]) -> str:
        """Determine the overall trend direction.

        Uses a combination of:
        - Slope of pass rates over time
        - Net regressions vs improvements
        """
        if not pass_rates or len(pass_rates) < 2:
            if not regressions and not improvements:
                return TrendDirection.STABLE
            return TrendDirection.IMPROVING if improvements else TrendDirection.DEGRADING

        # Compute slope of pass rates
        rates = [pr for _, pr in pass_rates]
        n = len(rates)

        # Simple linear regression slope
        x_mean = (n - 1) / 2
        y_mean = sum(rates) / n
        numerator = sum((i - x_mean) * (rates[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        # Net regression metric
        net_change = len(improvements) - len(regressions)

        # Decide direction
        # Significant slope threshold (percent per run)
        if slope > 2.0 and net_change >= 0:
            return TrendDirection.IMPROVING
        elif slope < -2.0 and net_change <= 0:
            return TrendDirection.DEGRADING
        elif abs(slope) <= 2.0 and abs(net_change) <= 1:
            return TrendDirection.STABLE
        elif net_change > 1:
            return TrendDirection.IMPROVING
        elif net_change < -1:
            return TrendDirection.DEGRADING
        else:
            return TrendDirection.STABLE

    def _compute_volatility(self, pass_rates: List[Tuple[str, float]]) -> float:
        """Compute standard deviation of pass rates."""
        if len(pass_rates) < 2:
            return 0.0

        rates = [pr for _, pr in pass_rates]
        mean = sum(rates) / len(rates)
        variance = sum((r - mean) ** 2 for r in rates) / len(rates)
        return round(variance ** 0.5, 1)

    def _compute_category_trends(self, history: List[TestExecutionResult]
                                  ) -> Dict[str, Dict]:
        """Compute per-category pass rates and trends."""
        by_category = defaultdict(list)
        for r in history:
            by_category[r.category].append(r)

        per_category = {}
        for cat, results in by_category.items():
            passed = sum(1 for r in results if r.status in ("PASS",))
            per_category[cat] = {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "pass_rate": round((passed / len(results)) * 100, 1) if results else 0.0,
            }

        return per_category

    def _generate_trend_recommendation(self, direction: str,
                                        regressions: List[str],
                                        improvements: List[str],
                                        pass_rate: float,
                                        volatility: float) -> str:
        """Generate a human-readable recommendation based on trend."""
        if direction == TrendDirection.DEGRADING:
            rec = (
                f"⚠️ Tests are DEGRADING — the pass rate is declining. "
                f"Immediate attention is needed. "
            )
            if regressions:
                rec += f"Investigate {len(regressions)} new regressions: "
                rec += ", ".join(regressions[:5])
                if len(regressions) > 5:
                    rec += f" (+{len(regressions) - 5} more)"
                rec += ". "
            rec += "Review recent code changes and re-run the affected tests."
        elif direction == TrendDirection.IMPROVING:
            rec = (
                f"✅ Tests are IMPROVING — the pass rate is trending upward. "
            )
            if improvements:
                rec += f"{len(improvements)} previously failing tests are now passing. "
            rec += "Continue current development practices."
        else:
            rec = (
                f"➡️ Tests are STABLE with a {pass_rate:.1f}% pass rate. "
            )
            if volatility > 10:
                rec += (
                    f"However, pass rates are volatile (σ={volatility:.1f}%), "
                    "which may indicate flaky tests. Consider stabilizing flaky tests."
                )
            else:
                rec += "No significant changes detected — maintain test quality."

        return rec

    # ─────────────────────────────────────────────────────────
    # 3. Bug Report Generator
    # ─────────────────────────────────────────────────────────

    def generate_bug_report(self, result: TestExecutionResult,
                             judgement: Optional[JudgementResult] = None) -> BugReport:
        """Generate a structured bug report from a failed test + judgement.

        Args:
            result: The failed TestExecutionResult
            judgement: Optional JudgementResult from judge.py

        Returns:
            BugReport with all structured fields populated
        """
        # First, perform root cause analysis
        analysis = self.analyze_failure(result)

        # Determine severity
        severity = self._determine_severity(result, analysis)

        # Build steps to reproduce
        steps = self._extract_reproduction_steps(result)

        # Expected vs actual
        expected = self._extract_expected_behavior(result)
        actual = self._extract_actual_behavior(result, analysis)

        # Build title
        title = self._build_bug_title(result, analysis)

        # Collect screenshot paths
        screenshots = []
        for step in result.step_results:
            if step.screenshot_path:
                screenshots.append(step.screenshot_path)

        # Judgement summary
        judgement_summary = ""
        if judgement:
            judgement_summary = (
                f"Verdict: {judgement.overall_verdict} (confidence: {judgement.confidence:.1%}). "
                f"Checks: {judgement.pass_checks}P/{judgement.fail_checks}F/{judgement.warn_checks}W/{judgement.skip_checks}S. "
            )
            if hasattr(judgement, 'issues') and judgement.issues:
                judgement_summary += f"Issues: {'; '.join(judgement.issues[:3])}. "
            if hasattr(judgement, 'suggestions') and judgement.suggestions:
                judgement_summary += f"Suggestions: {'; '.join(judgement.suggestions[:2])}."

        # Suggested fix (from analysis)
        suggested_fix = " | ".join(analysis.suggestions[:3]) if analysis.suggestions else ""

        # Environment info
        environment = {
            "source_page": result.source_page,
            "test_category": result.category,
            "priority": result.priority,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "total_duration_ms": str(result.total_duration_ms),
        }

        report = BugReport(
            title=title,
            severity=severity,
            test_case_id=result.test_case_id,
            category=result.category,
            status="NEW",
            steps_to_reproduce=steps,
            expected_behavior=expected,
            actual_behavior=actual,
            screenshot_paths=screenshots,
            suggested_fix=suggested_fix,
            root_cause=analysis.root_cause_label,
            judgement_summary=judgement_summary,
            environment=environment,
        )

        return report

    def _determine_severity(self, result: TestExecutionResult,
                             analysis: FailureAnalysis) -> str:
        """Determine bug severity based on test priority and failure type."""
        priority = result.priority.upper()
        category = analysis.root_cause_category

        # P0 failures are always CRITICAL
        if priority == "P0":
            return "CRITICAL"

        # P1 + API_ERROR or PAGE_LOAD_ERROR → CRITICAL
        if priority == "P1" and category in (FailureCategory.API_ERROR,
                                              FailureCategory.PAGE_LOAD_ERROR):
            return "CRITICAL"

        # P1 other failures → MAJOR
        if priority == "P1":
            return "MAJOR"

        # P2 → MAJOR
        if priority == "P2":
            return "MAJOR"

        # P3 → MINOR
        if priority == "P3":
            return "MINOR"

        # All failures in a total FAIL → MAJOR
        if result.status == "FAIL":
            return "MAJOR"

        # Default
        return "MINOR"

    def _extract_reproduction_steps(self, result: TestExecutionResult) -> List[str]:
        """Extract numbered steps to reproduce from the test result."""
        steps = []

        steps.append(f"1. Navigate to: {result.source_page}")

        for i, step in enumerate(result.step_results):
            action = step.step_action
            target = step.step_target
            value = step.step_value
            desc = step.step_description or f"{action} {target}"

            if action == "navigate":
                steps.append(f"{len(steps) + 1}. Navigate to: {target}")
            elif action == "type":
                steps.append(f"{len(steps) + 1}. In '{target}', type '{value}'")
            elif action == "click":
                steps.append(f"{len(steps) + 1}. Click on '{target}'")
            elif action == "select":
                steps.append(f"{len(steps) + 1}. In '{target}', select '{value}'")
            elif action == "wait":
                steps.append(f"{len(steps) + 1}. Wait for {value}ms")
            elif action == "verify":
                steps.append(f"{len(steps) + 1}. Verify: {desc}")
            elif action == "scroll":
                steps.append(f"{len(steps) + 1}. Scroll: {value or 'down'}")
            else:
                steps.append(f"{len(steps) + 1}. {desc}")

            # Mark failures
            if step.status == "FAIL":
                steps[-1] += f" ❌ FAILED — {step.error_message[:80]}"

        return steps

    def _extract_expected_behavior(self, result: TestExecutionResult) -> str:
        """Extract expected behavior from the test result."""
        parts = []
        parts.append(f"Test case '{result.test_case_name}' should pass all steps.")

        # Check verify_result of passing steps for expectations
        for step in result.step_results:
            if step.status in ("PASS", "HEALED") and step.verify_result:
                # Extract ✅ lines
                for line in step.verify_result.split(";"):
                    if "✅" in line:
                        parts.append(line.strip())

        if len(parts) == 1:
            # No detailed expectations found
            parts.append(f"All {result.total_steps} steps should complete successfully.")

        return " ".join(parts)

    def _extract_actual_behavior(self, result: TestExecutionResult,
                                   analysis: FailureAnalysis) -> str:
        """Extract actual behavior / failure description."""
        parts = []

        parts.append(f"Test '{result.test_case_id}' failed with status '{result.status}'.")

        if analysis.root_cause_category != FailureCategory.UNKNOWN:
            parts.append(
                f"Root cause: {analysis.root_cause_label} "
                f"(confidence: {analysis.confidence:.0%})."
            )

        if result.error_summary:
            parts.append(f"Error: {result.error_summary}")

        # Add specific failed step details
        for step in analysis.failed_steps[:3]:
            err = step.error_message[:100] if step.error_message else "No error message"
            parts.append(
                f"Step {step.step_index + 1} ({step.step_action} {step.step_target}): {err}"
            )

        return " ".join(parts)

    def _build_bug_title(self, result: TestExecutionResult,
                           analysis: FailureAnalysis) -> str:
        """Build a concise bug title."""
        cat_label = analysis.root_cause_label
        tc_name = result.test_case_name or result.test_case_id
        # Limit length
        if len(tc_name) > 60:
            tc_name = tc_name[:57] + "..."

        return f"[{cat_label}] {tc_name}"

    # ─────────────────────────────────────────────────────────
    # 4. Serialization Helpers
    # ─────────────────────────────────────────────────────────

    def save_bug_report(self, bug: BugReport, path: str) -> str:
        """Save a BugReport to a JSON file.

        Args:
            bug: The BugReport instance to save
            path: File path (e.g., 'reports/bugs/bug-001.json')

        Returns:
            The absolute path of the saved file
        """
        if not isinstance(bug, BugReport):
            raise TypeError(f"Expected BugReport, got {type(bug).__name__}")

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(bug.to_dict(), f, ensure_ascii=False, indent=2)

        return os.path.abspath(path)

    @staticmethod
    def save_analysis(analysis: FailureAnalysis, path: str) -> str:
        """Save a FailureAnalysis to a JSON file.

        Args:
            analysis: The FailureAnalysis instance
            path: File path

        Returns:
            The absolute path of the saved file
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(analysis.to_dict(), f, ensure_ascii=False, indent=2)

        return os.path.abspath(path)

    @staticmethod
    def save_trend_report(report: TrendReport, path: str) -> str:
        """Save a TrendReport to a JSON file.

        Args:
            report: The TrendReport instance
            path: File path

        Returns:
            The absolute path of the saved file
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        return os.path.abspath(path)

    @staticmethod
    def load_bug_report(path: str) -> BugReport:
        """Load a BugReport from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure list fields are properly typed
        data.setdefault("steps_to_reproduce", [])
        data.setdefault("screenshot_paths", [])
        data.setdefault("environment", {})

        return BugReport(**{k: v for k, v in data.items()
                            if k in BugReport.__dataclass_fields__})

    # ─────────────────────────────────────────────────────────
    # 5. Bulk Analysis Convenience Methods
    # ─────────────────────────────────────────────────────────

    def analyze_all_failures(self, results: List[TestExecutionResult]
                              ) -> List[FailureAnalysis]:
        """Analyze all failed results in a batch.

        Args:
            results: List of TestExecutionResult (mixed pass/fail)

        Returns:
            List of FailureAnalysis for all failed results
        """
        analyses = []
        for result in results:
            if result.status in ("FAIL", "PARTIAL"):
                try:
                    analysis = self.analyze_failure(result)
                    analyses.append(analysis)
                except Exception as e:
                    # Create a minimal analysis on error
                    analyses.append(FailureAnalysis(
                        root_cause_category=FailureCategory.UNKNOWN,
                        details={"error": str(e), "test_case_id": result.test_case_id},
                        suggestions=[f"Analysis error: {e}"],
                    ))
        return analyses

    def generate_bug_reports_batch(self, results: List[TestExecutionResult],
                                     judgement: Optional[JudgementResult] = None
                                     ) -> List[BugReport]:
        """Generate bug reports for all failed results.

        Args:
            results: List of TestExecutionResult
            judgement: Optional single judgement (applied to all)

        Returns:
            List of BugReport for all failed results
        """
        bugs = []
        for result in results:
            if result.status in ("FAIL", "PARTIAL"):
                try:
                    bug = self.generate_bug_report(result, judgement)
                    bugs.append(bug)
                except Exception as e:
                    # Create a minimal bug report
                    bugs.append(BugReport(
                        title=f"Analysis Error: {result.test_case_id}",
                        severity="MINOR",
                        test_case_id=result.test_case_id,
                        category=result.category,
                        actual_behavior=f"Failed to generate report: {e}",
                    ))
        return bugs

    def summary(self, analyses: List[FailureAnalysis]) -> Dict[str, Any]:
        """Generate a summary of failure analyses.

        Args:
            analyses: List of FailureAnalysis

        Returns:
            Dict with category counts and key findings
        """
        if not analyses:
            return {"total": 0, "by_category": {}, "top_suggestions": []}

        category_counts = Counter(a.root_cause_category for a in analyses)
        all_suggestions = []
        for a in analyses:
            all_suggestions.extend(a.suggestions)

        # Count most frequent suggestions
        suggestion_counts = Counter(all_suggestions).most_common(5)

        return {
            "total": len(analyses),
            "by_category": {
                cat: {"count": count,
                      "label": FailureCategory.label(cat)}
                for cat, count in category_counts.most_common()
            },
            "top_suggestions": [
                {"suggestion": s, "count": c}
                for s, c in suggestion_counts
            ],
        }
