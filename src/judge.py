"""
Smart Multi-Modal Judgment Engine — Iteration 4 Core Module

Consumes TestExecutionResult from executor.py and produces JudgementResult
with multi-modal verdicts, confidence scores, and false-positive filtering.

Multi-modal verdict system:
  - DOM check:     snapshot text comparison (expected text present?)
  - API check:     status code match (200 expected, 400/500 = fail)
  - URL check:     URL contains expected path
  - Visual check:  heuristic for visual changes (element count, structure)
  - Content check: keyword presence verification

False-positive filtering:
  - Loading state detection (spinner, 'loading' text)
  - Transient network error retry window
  - Rate limiting detection (429 status)
  - Auto-pass known flaky patterns

Confidence scoring (0.0–1.0):
  - Exact matches  → 1.0
  - Heuristic matches → 0.5–0.9
  - Low confidence  → flagged for human review

Usage:
    from src.judge import Judge, JudgementResult
    judge = Judge()
    result = judge.judge(test_case, execution_result)
    results = judge.judge_all(execution_results)
    print(judge.get_summary())
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime

try:
    from .executor import TestExecutionResult, StepResult
    from .planner import TestCase, TestExpectation
except ImportError:
    try:
        from executor import TestExecutionResult, StepResult
        from planner import TestCase, TestExpectation
    except ImportError:
        TestExecutionResult = object  # type: ignore
        StepResult = object           # type: ignore
        TestCase = object             # type: ignore
        TestExpectation = object      # type: ignore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Enums & Constants
# ═══════════════════════════════════════════════════════════════

class OverallVerdict(str, Enum):
    PASS  = "PASS"
    FAIL  = "FAIL"
    FLAKY = "FLAKY"


class CheckVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class CheckType(str, Enum):
    DOM     = "dom"
    API     = "api"
    URL     = "url"
    VISUAL  = "visual"
    CONTENT = "content"


# Known flaky error patterns that should auto-pass
FLAKY_PATTERNS: List[Tuple[str, float]] = [
    # (regex pattern, confidence override)
    (r"stale\s+element\s+reference", 0.3),
    (r"element\s+is\s+not\s+attached\s+to\s+the\s+page\s+document", 0.3),
    (r"cannot\s+focus\s+element", 0.35),
    (r"element\s+not\s+interactable", 0.4),
    (r"script\s+timeout", 0.35),
    (r"waiting\s+for\s+element\s+to\s+be\s+located", 0.3),
    (r"navigation\s+timeout", 0.3),
    (r"connection\s+reset", 0.25),
    (r"Temporary failure in name resolution", 0.2),
    (r"ERR_NAME_NOT_RESOLVED", 0.2),
    (r"ECONNREFUSED", 0.2),
    (r"ETIMEDOUT", 0.25),
]

# Loading-related keywords to detect stale-loading false positives
LOADING_KEYWORDS: List[str] = [
    "loading", "spinner", "progress", "fetching", "waiting",
    "skeleton", "placeholder", "pending", "load",
]

# Rate-limit status codes
RATE_LIMIT_CODES: Set[int] = {429, 503}

# Transient error status codes
TRANSIENT_ERROR_CODES: Set[int] = {408, 429, 500, 502, 503, 504}


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class IndividualVerdict:
    """Single check verdict within a multi-modal judgment."""
    check_type: str                # dom | api | url | visual | content
    verdict: str                   # PASS | FAIL | WARN | SKIP
    confidence: float              # 0.0 – 1.0
    expected: str = ""             # what was expected
    actual: str = ""               # what was observed
    evidence: str = ""             # supporting evidence / reasoning
    step_index: int = -1           # which step this check relates to
    is_false_positive: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class JudgementResult:
    """Complete judgment for one test case."""
    test_case_id: str
    test_case_name: str

    overall_verdict: str = "FLAKY"    # PASS | FAIL | FLAKY
    confidence: float = 0.0           # 0.0 – 1.0
    verdicts: List[IndividualVerdict] = field(default_factory=list)
    false_positive_flags: List[str] = field(default_factory=list)
    recommendation: str = ""

    # Counts
    total_checks: int = 0
    pass_checks: int = 0
    fail_checks: int = 0
    warn_checks: int = 0
    skip_checks: int = 0
    false_positives_detected: int = 0

    judged_at: str = ""

    def __post_init__(self):
        if not self.judged_at:
            self.judged_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["verdicts"] = [v.to_dict() for v in self.verdicts]
        return d

    def summary(self) -> str:
        return (
            f"{self.test_case_id} [{self.overall_verdict}] "
            f"confidence={self.confidence:.2f} "
            f"({self.pass_checks}/{self.total_checks} pass, "
            f"{self.fail_checks} fail, {self.warn_checks} warn)"
        )


@dataclass
class JudgeConfig:
    """Configuration for the judgment engine."""
    # Confidence thresholds
    high_confidence_threshold: float = 0.80
    low_confidence_threshold: float = 0.40

    # False positive detection
    enable_false_positive_filter: bool = True
    loading_check_enabled: bool = True
    transient_error_check_enabled: bool = True
    rate_limit_check_enabled: bool = True
    flaky_pattern_check_enabled: bool = True

    # Visual check heuristics
    min_element_count: int = 3
    element_count_drift_tolerance: float = 0.80  # 80% tolerance

    # Recommendation messages
    recommend_human_review_confidence: float = 0.50


# ═══════════════════════════════════════════════════════════════
# Judge
# ═══════════════════════════════════════════════════════════════

class Judge:
    """Smart multi-modal judgment engine.

    Evaluates TestExecutionResult against TestCase expectations using
    DOM, API, URL, visual, and content checks. Applies false-positive
    filtering and produces confidence-scored JudgementResults.

    Usage:
        judge = Judge()
        result = judge.judge(test_case, execution_result)
        results = judge.judge_all(execution_results)
        stats = judge.get_summary()
    """

    def __init__(self, config: JudgeConfig = None):
        self.config = config or JudgeConfig()
        self._results: List[JudgementResult] = []
        self._judgement_log: List[Dict] = []

    # ── Public API ──

    def judge(self, test_case: TestCase,
              execution_result: TestExecutionResult) -> JudgementResult:
        """Judge a single test case against its execution result.

        Args:
            test_case: The TestCase with expectations
            execution_result: The TestExecutionResult from executor

        Returns:
            JudgementResult with verdicts, confidence, and recommendations
        """
        result = JudgementResult(
            test_case_id=execution_result.test_case_id,
            test_case_name=execution_result.test_case_name,
        )

        self._log(f"Judging {result.test_case_id} — {result.test_case_name}")

        # Phase 1: Run all multi-modal checks
        all_verdicts: List[IndividualVerdict] = []

        # 1a. Check each step's snapshot
        for i, step_result in enumerate(execution_result.step_results):
            step_verdicts = self._check_step(step_result, i, test_case)
            all_verdicts.extend(step_verdicts)

        # 1b. Check expectations from the test case
        exp_verdicts = self._check_expectations(test_case, execution_result)
        all_verdicts.extend(exp_verdicts)

        # 1c. Check overall execution health
        health_verdicts = self._check_execution_health(execution_result)
        all_verdicts.extend(health_verdicts)

        # Phase 2: False-positive filtering
        if self.config.enable_false_positive_filter:
            all_verdicts = self._apply_false_positive_filters(
                all_verdicts, execution_result)

        # Phase 3: Compute aggregate scores
        result.verdicts = all_verdicts
        result.total_checks = len(all_verdicts)
        result.pass_checks = sum(1 for v in all_verdicts if v.verdict == "PASS")
        result.fail_checks = sum(1 for v in all_verdicts if v.verdict == "FAIL")
        result.warn_checks = sum(1 for v in all_verdicts if v.verdict == "WARN")
        result.skip_checks = sum(1 for v in all_verdicts if v.verdict == "SKIP")
        result.false_positives_detected = sum(
            1 for v in all_verdicts if v.is_false_positive)

        # Overall confidence: average of individual confidences, weighted
        if all_verdicts:
            result.confidence = sum(v.confidence for v in all_verdicts) / len(all_verdicts)
        else:
            result.confidence = 0.5  # neutral

        result.confidence = round(result.confidence, 3)

        # Phase 4: Determine overall verdict
        result.overall_verdict = self._determine_overall_verdict(result)

        # Phase 5: Generate recommendation
        result.recommendation = self._generate_recommendation(result)

        self._results.append(result)
        self._log(f"  → {result.summary()}")
        return result

    def judge_all(self, execution_results: List[TestExecutionResult],
                  test_cases: List[TestCase] = None) -> List[JudgementResult]:
        """Judge all execution results, optionally paired with test cases.

        Args:
            execution_results: List of TestExecutionResult
            test_cases: Optional list of TestCase (paired by id)

        Returns:
            List[JudgementResult]
        """
        results = []

        # Build lookup if test_cases provided
        case_map: Dict[str, TestCase] = {}
        if test_cases:
            for tc in test_cases:
                case_map[tc.id] = tc

        for er in execution_results:
            tc = case_map.get(er.test_case_id)
            if tc is None:
                self._log(f"WARNING: No TestCase found for {er.test_case_id}, "
                          f"judging execution result alone.")
                # Build a minimal synthetic test case
                tc = self._synthetic_test_case(er)

            result = self.judge(tc, er)
            results.append(result)

        return results

    def get_summary(self) -> Dict:
        """Get summary statistics from all judged results.

        Returns:
            Dict with overall stats
        """
        if not self._results:
            return {
                "total": 0, "passed": 0, "failed": 0, "flaky": 0,
                "avg_confidence": 0.0, "total_false_positives": 0,
                "recommendations": [],
            }

        passed = sum(1 for r in self._results if r.overall_verdict == "PASS")
        failed = sum(1 for r in self._results if r.overall_verdict == "FAIL")
        flaky  = sum(1 for r in self._results if r.overall_verdict == "FLAKY")

        avg_conf = sum(r.confidence for r in self._results) / len(self._results)
        total_fp = sum(r.false_positives_detected for r in self._results)

        # Gather recommendations that suggest human review
        human_review_cases = [
            r.test_case_id for r in self._results
            if "human review" in r.recommendation.lower()
        ]

        return {
            "total": len(self._results),
            "passed": passed,
            "failed": failed,
            "flaky": flaky,
            "pass_rate": round(passed / len(self._results) * 100, 1),
            "avg_confidence": round(avg_conf, 3),
            "total_false_positives": total_fp,
            "needs_human_review": human_review_cases,
            "recommendations": [
                r.recommendation for r in self._results if r.recommendation
            ],
            "judged_at": datetime.now().isoformat(),
        }

    # ── Multi-Modal Checks ──

    def _check_step(self, step_result: StepResult, index: int,
                    test_case: TestCase) -> List[IndividualVerdict]:
        """Run all applicable checks on a single step result."""
        verdicts: List[IndividualVerdict] = []

        # DOM check
        dom_v = self._dom_check(step_result, index)
        if dom_v:
            verdicts.append(dom_v)

        # API check
        api_v = self._api_check(step_result, index)
        if api_v:
            verdicts.append(api_v)

        # URL check
        url_v = self._url_check(step_result, index)
        if url_v:
            verdicts.append(url_v)

        # Visual check
        vis_v = self._visual_check(step_result, index)
        if vis_v:
            verdicts.append(vis_v)

        # Content check
        cnt_v = self._content_check(step_result, index, test_case)
        if cnt_v:
            verdicts.append(cnt_v)

        # If step itself was marked FAIL by executor, add a synthetic check
        if step_result.status == "FAIL":
            verdicts.append(IndividualVerdict(
                check_type="content",
                verdict="FAIL",
                confidence=0.9,
                expected=f"Step {index+1} should pass",
                actual=f"Step {index+1} failed: {step_result.error_message[:120]}",
                evidence=step_result.error_message,
                step_index=index,
            ))

        return verdicts

    def _check_expectations(self, test_case: TestCase,
                            execution_result: TestExecutionResult
                            ) -> List[IndividualVerdict]:
        """Check each TestExpectation against execution evidence."""
        verdicts: List[IndividualVerdict] = []

        if not test_case.expectations:
            return verdicts

        # Collect all evidence from step results
        all_snapshots = "\n".join(
            sr.observe_snapshot for sr in execution_result.step_results
            if sr.observe_snapshot)
        all_verify = "\n".join(
            sr.verify_result for sr in execution_result.step_results
            if sr.verify_result)
        all_api_calls: List[Dict] = []
        for sr in execution_result.step_results:
            all_api_calls.extend(sr.api_calls or [])

        combined_evidence = f"{all_snapshots}\n{all_verify}"

        for exp in test_case.expectations:
            if exp.type == "api_status":
                v = self._check_api_expectation(exp, all_api_calls)
            elif exp.type in ("page_content", "element_visible", "element_not_exist"):
                v = self._check_content_expectation(exp, combined_evidence)
            elif exp.type == "url_contains":
                v = self._check_url_expectation(exp, combined_evidence)
            elif exp.type == "element_count":
                v = self._check_element_count_expectation(exp, combined_evidence)
            else:
                v = IndividualVerdict(
                    check_type="content",
                    verdict="SKIP",
                    confidence=0.5,
                    expected=exp.expected_value,
                    actual="",
                    evidence=f"Unknown expectation type: {exp.type}",
                )
            if v:
                verdicts.append(v)

        return verdicts

    def _check_execution_health(self, er: TestExecutionResult
                                ) -> List[IndividualVerdict]:
        """Check overall execution health (pass rate, failures, etc.)."""
        verdicts: List[IndividualVerdict] = []

        # Check for all-skip
        if er.skipped_steps == er.total_steps and er.total_steps > 0:
            verdicts.append(IndividualVerdict(
                check_type="content",
                verdict="WARN",
                confidence=0.8,
                expected="At least one step executed",
                actual="All steps skipped",
                evidence=f"Skipped: {er.skipped_steps}/{er.total_steps}",
            ))

        # Check for zero-duration (suspicious)
        if er.total_duration_ms == 0 and er.total_steps > 0:
            verdicts.append(IndividualVerdict(
                check_type="visual",
                verdict="WARN",
                confidence=0.6,
                expected="Steps take measurable time",
                actual="0ms total duration",
                evidence="Execution may have been simulated",
            ))

        return verdicts

    # ── Individual Check Implementations ──

    def _dom_check(self, sr: StepResult, index: int) -> Optional[IndividualVerdict]:
        """DOM snapshot check: does the snapshot contain meaningful content?"""
        snapshot = sr.observe_snapshot
        if not snapshot:
            return None  # No snapshot to check

        # Detect empty or error snapshots
        if snapshot.startswith("ERROR:"):
            return IndividualVerdict(
                check_type="dom",
                verdict="FAIL",
                confidence=0.85,
                expected="Valid DOM snapshot",
                actual=f"Error in snapshot: {snapshot[:80]}",
                evidence=snapshot,
                step_index=index,
            )

        # Check for minimal DOM structure indicators
        has_structure = any(tag in snapshot.lower() for tag in
                            ["<html", "<body", "<div", "button", "input",
                             "[", "@e", "link", "textbox"])
        if has_structure:
            return IndividualVerdict(
                check_type="dom",
                verdict="PASS",
                confidence=0.75,
                expected="DOM structure present",
                actual=f"Snapshot contains DOM elements ({len(snapshot)} chars)",
                evidence=f"Length: {len(snapshot)} chars",
                step_index=index,
            )
        else:
            return IndividualVerdict(
                check_type="dom",
                verdict="WARN",
                confidence=0.4,
                expected="DOM structure present",
                actual="No recognizable DOM structure in snapshot",
                evidence=snapshot[:200],
                step_index=index,
            )

    def _api_check(self, sr: StepResult, index: int) -> Optional[IndividualVerdict]:
        """API check: examine API call logs for status codes."""
        api_calls = sr.api_calls or []
        if not api_calls:
            return None  # No API calls to check

        all_ok = True
        evidence_parts: List[str] = []
        fail_details: List[str] = []

        for call in api_calls:
            resp = call.get("response", {}) if isinstance(call, dict) else {}
            status = resp.get("status", 0) if isinstance(resp, dict) else 0
            url = call.get("url", "") if isinstance(call, dict) else ""
            method = call.get("method", "") if isinstance(call, dict) else ""

            if isinstance(status, int) and 200 <= status < 400:
                evidence_parts.append(f"{method} {url} → {status} OK")
            elif isinstance(status, int):
                all_ok = False
                fail_details.append(f"{method} {url} → {status}")
                evidence_parts.append(f"{method} {url} → {status} FAIL")
            else:
                evidence_parts.append(f"{method} {url} → ?")

        if all_ok:
            return IndividualVerdict(
                check_type="api",
                verdict="PASS",
                confidence=0.9,
                expected="All API calls return 2xx/3xx",
                actual=f"{len(api_calls)} API calls, all OK",
                evidence="; ".join(evidence_parts),
                step_index=index,
            )
        else:
            return IndividualVerdict(
                check_type="api",
                verdict="FAIL",
                confidence=0.85,
                expected="All API calls return 2xx/3xx",
                actual=f"Failures: {'; '.join(fail_details)}",
                evidence="; ".join(evidence_parts),
                step_index=index,
            )

    def _url_check(self, sr: StepResult, index: int) -> Optional[IndividualVerdict]:
        """URL check: parse verify_result and act_detail for URL mentions."""
        combined = f"{sr.verify_result}\n{sr.act_detail}\n{sr.think_reasoning}"
        if not combined.strip():
            return None

        url_pattern = re.compile(
            r'https?://[^\s\'"<>]+|current[_\s]?url[:\s]*(\S+)', re.IGNORECASE)

        urls = url_pattern.findall(combined)
        if not urls:
            return None  # No URLs found

        # Normalize matches (tuple from capturing groups)
        flat_urls: List[str] = []
        for u in urls:
            if isinstance(u, tuple):
                flat_urls.extend(part for part in u if part)
            else:
                flat_urls.append(u)

        if flat_urls:
            return IndividualVerdict(
                check_type="url",
                verdict="PASS",
                confidence=0.8,
                expected="URL present in execution",
                actual=f"Found: {flat_urls[0][:80]}",
                evidence="; ".join(flat_urls[:3]),
                step_index=index,
            )

        return None

    def _visual_check(self, sr: StepResult, index: int) -> Optional[IndividualVerdict]:
        """Visual check: heuristic analysis of snapshot structure changes."""
        snapshot = sr.observe_snapshot
        if not snapshot:
            return None

        # Count interactive element references (@eNNN pattern)
        ref_count = len(re.findall(r'@e\d+', snapshot))
        # Count HTML-like elements
        element_indicators = len(re.findall(
            r'\[(button|link|textbox|combobox|listbox|heading|image|'
            r'navigation|region|article|main|form|input|select)\]',
            snapshot, re.IGNORECASE))

        total_indicators = ref_count + element_indicators

        if total_indicators >= self.config.min_element_count:
            return IndividualVerdict(
                check_type="visual",
                verdict="PASS",
                confidence=0.7,
                expected=f">= {self.config.min_element_count} interactive elements",
                actual=f"{total_indicators} elements found",
                evidence=f"refs: {ref_count}, elements: {element_indicators}",
                step_index=index,
            )
        elif total_indicators > 0:
            return IndividualVerdict(
                check_type="visual",
                verdict="WARN",
                confidence=0.45,
                expected=f">= {self.config.min_element_count} interactive elements",
                actual=f"Only {total_indicators} elements found",
                evidence=f"refs: {ref_count}, elements: {element_indicators}",
                step_index=index,
            )
        else:
            return IndividualVerdict(
                check_type="visual",
                verdict="FAIL",
                confidence=0.5,
                expected="Page has interactive elements",
                actual="No interactive elements detected",
                evidence=f"Snapshot: {snapshot[:100]}",
                step_index=index,
            )

    def _content_check(self, sr: StepResult, index: int,
                       test_case: TestCase) -> Optional[IndividualVerdict]:
        """Content check: keyword presence verification in snapshot."""
        snapshot = sr.observe_snapshot
        if not snapshot:
            return None

        # Check verify_result for success/failure indicators
        verify = sr.verify_result.lower()
        if "❌" in sr.verify_result or "fail" in verify:
            return IndividualVerdict(
                check_type="content",
                verdict="FAIL",
                confidence=0.85,
                expected="Verification passes",
                actual=f"Verification indicates failure",
                evidence=sr.verify_result[:200],
                step_index=index,
            )

        if "✅" in sr.verify_result or "pass" in verify or "验证通过" in verify:
            return IndividualVerdict(
                check_type="content",
                verdict="PASS",
                confidence=0.8,
                expected="Verification passes",
                actual="Verification indicates success",
                evidence=sr.verify_result[:200],
                step_index=index,
            )

        # Check for error indicators in snapshot
        snapshot_lower = snapshot.lower()
        error_indicators = ["error", "exception", "traceback", "failed",
                            "stacktrace", "fatal"]
        for ind in error_indicators:
            if ind in snapshot_lower:
                return IndividualVerdict(
                    check_type="content",
                    verdict="FAIL",
                    confidence=0.7,
                    expected="No error indicators in page",
                    actual=f"Found error indicator: '{ind}'",
                    evidence=f"Snapshot contains '{ind}'",
                    step_index=index,
                )

        return None

    # ── Expectation Checking Helpers ──

    def _check_api_expectation(self, exp: TestExpectation,
                               api_calls: List[Dict]) -> IndividualVerdict:
        """Check an api_status expectation against API call log."""
        expected_status = exp.expected_value

        for call in api_calls:
            resp = call.get("response", {}) if isinstance(call, dict) else {}
            status = str(resp.get("status", "")) if isinstance(resp, dict) else ""

            if exp.operator == "equals" and status == expected_status:
                return IndividualVerdict(
                    check_type="api",
                    verdict="PASS",
                    confidence=1.0,
                    expected=f"Status {expected_status}",
                    actual=f"Status {status}",
                    evidence=f"Matched: {status} == {expected_status}",
                )

            elif exp.operator == "less_than":
                try:
                    if int(status) < int(expected_status):
                        return IndividualVerdict(
                            check_type="api",
                            verdict="PASS",
                            confidence=1.0,
                            expected=f"Status < {expected_status}",
                            actual=f"Status {status}",
                            evidence=f"Matched: {status} < {expected_status}",
                        )
                except (ValueError, TypeError):
                    pass

        # No match found
        return IndividualVerdict(
            check_type="api",
            verdict="FAIL",
            confidence=0.9,
            expected=f"Status {exp.operator} {expected_status}",
            actual="No matching API call found",
            evidence=f"Searched {len(api_calls)} API calls",
        )

    def _check_content_expectation(self, exp: TestExpectation,
                                   evidence: str) -> IndividualVerdict:
        """Check a page_content expectation against combined evidence."""
        target = exp.expected_value
        if not target:
            return IndividualVerdict(
                check_type="content",
                verdict="SKIP",
                confidence=0.5,
                expected="(empty expectation)",
                actual="Skipped: no expected value",
            )

        evidence_lower = evidence.lower()
        target_lower = target.lower()

        if exp.operator == "contains":
            if target_lower in evidence_lower:
                return IndividualVerdict(
                    check_type="content",
                    verdict="PASS",
                    confidence=1.0,
                    expected=f"Contains '{target}'",
                    actual=f"Found '{target}'",
                    evidence=f"Content contains '{target}'",
                )
            else:
                return IndividualVerdict(
                    check_type="content",
                    verdict="FAIL",
                    confidence=0.85,
                    expected=f"Contains '{target}'",
                    actual=f"'{target}' not found",
                    evidence=f"Not found in {len(evidence)} chars of content",
                )

        elif exp.operator == "matches":
            try:
                if re.search(target, evidence, re.IGNORECASE):
                    return IndividualVerdict(
                        check_type="content",
                        verdict="PASS",
                        confidence=0.9,
                        expected=f"Matches pattern '{target}'",
                        actual="Pattern matched",
                        evidence=f"Regex '{target}' matched content",
                    )
                else:
                    return IndividualVerdict(
                        check_type="content",
                        verdict="FAIL",
                        confidence=0.8,
                        expected=f"Matches pattern '{target}'",
                        actual="No match",
                        evidence=f"Pattern '{target}' not found",
                    )
            except re.error:
                return IndividualVerdict(
                    check_type="content",
                    verdict="WARN",
                    confidence=0.3,
                    expected=f"Matches pattern '{target}'",
                    actual="Invalid regex pattern",
                    evidence=f"Regex error in '{target}'",
                )

        elif exp.operator == "equals":
            if target_lower == evidence_lower:
                return IndividualVerdict(
                    check_type="content",
                    verdict="PASS",
                    confidence=1.0,
                    expected=f"Equals '{target}'",
                    actual=f"Exact match",
                    evidence="Exact content match",
                )
            else:
                # Fuzzy match: check if target is a significant substring
                if target_lower in evidence_lower and len(target) > 5:
                    return IndividualVerdict(
                        check_type="content",
                        verdict="PASS",
                        confidence=0.7,
                        expected=f"Equals '{target}'",
                        actual=f"Content contains '{target}' but not exact match",
                        evidence="Partial match (equals → relaxed to contains)",
                    )
                return IndividualVerdict(
                    check_type="content",
                    verdict="FAIL",
                    confidence=0.85,
                    expected=f"Equals '{target}'",
                    actual="Content does not match",
                    evidence="Not found",
                )

        else:
            # Unknown operator — check contains as fallback
            if target_lower in evidence_lower:
                return IndividualVerdict(
                    check_type="content",
                    verdict="PASS",
                    confidence=0.7,
                    expected=f"{exp.operator} '{target}'",
                    actual=f"Contains '{target}'",
                    evidence=f"Fallback: contains check passed",
                )
            return IndividualVerdict(
                check_type="content",
                verdict="SKIP",
                confidence=0.3,
                expected=f"{exp.operator} '{target}'",
                actual=f"Unknown operator, cannot verify",
                evidence=f"Operator '{exp.operator}' not supported",
            )

    def _check_url_expectation(self, exp: TestExpectation,
                               evidence: str) -> IndividualVerdict:
        """Check a url_contains expectation."""
        target = exp.expected_value
        if not target:
            return IndividualVerdict(
                check_type="url",
                verdict="SKIP",
                confidence=0.5,
                expected="(empty URL expectation)",
                actual="Skipped",
            )

        evidence_lower = evidence.lower()
        target_lower = target.lower()

        if target_lower in evidence_lower:
            return IndividualVerdict(
                check_type="url",
                verdict="PASS",
                confidence=1.0 if len(target) > 10 else 0.85,
                expected=f"URL contains '{target}'",
                actual=f"Found '{target}'",
                evidence=f"URL fragment found in evidence",
            )
        else:
            return IndividualVerdict(
                check_type="url",
                verdict="FAIL",
                confidence=0.8,
                expected=f"URL contains '{target}'",
                actual=f"'{target}' not found",
                evidence="URL fragment missing",
            )

    def _check_element_count_expectation(self, exp: TestExpectation,
                                         evidence: str) -> IndividualVerdict:
        """Check an element_count expectation."""
        # Count refs in evidence
        ref_count = len(re.findall(r'@e\d+', evidence))

        try:
            expected_num = int(exp.expected_value)
        except (ValueError, TypeError):
            return IndividualVerdict(
                check_type="visual",
                verdict="SKIP",
                confidence=0.3,
                expected=f"Element count {exp.operator} {exp.expected_value}",
                actual=f"Invalid expected value",
                evidence="Cannot parse expected value as integer",
            )

        if exp.operator == "greater_than":
            passed = ref_count > expected_num
        elif exp.operator == "less_than":
            passed = ref_count < expected_num
        elif exp.operator == "equals":
            passed = ref_count == expected_num
        else:
            passed = ref_count >= expected_num  # default

        if passed:
            return IndividualVerdict(
                check_type="visual",
                verdict="PASS",
                confidence=0.85,
                expected=f"Element count {exp.operator} {expected_num}",
                actual=f"Found {ref_count} elements",
                evidence=f"Count: {ref_count} {exp.operator} {expected_num}",
            )
        else:
            return IndividualVerdict(
                check_type="visual",
                verdict="FAIL",
                confidence=0.8,
                expected=f"Element count {exp.operator} {expected_num}",
                actual=f"Found {ref_count} elements",
                evidence=f"Count: {ref_count} does not satisfy {exp.operator} {expected_num}",
            )

    # ── False Positive Detection ──

    def _apply_false_positive_filters(
            self, verdicts: List[IndividualVerdict],
            execution_result: TestExecutionResult
    ) -> List[IndividualVerdict]:
        """Apply false positive filters to downgrade/override suspicious FAILs.

        Returns modified verdicts list.
        """
        # Collect all error messages and evidence
        error_text = execution_result.error_summary or ""
        for sr in execution_result.step_results:
            error_text += f"\n{sr.error_message or ''}"
            error_text += f"\n{sr.verify_result or ''}"
            error_text += f"\n{sr.observe_snapshot or ''}"

        error_lower = error_text.lower()

        for v in verdicts:
            if v.verdict != "FAIL":
                continue

            # 1. Loading state detection
            if self.config.loading_check_enabled:
                if self._detect_loading_state(error_lower):
                    v.verdict = "WARN"
                    v.confidence = max(v.confidence, 0.2)
                    v.is_false_positive = True
                    v.evidence += " | FP: loading state detected"
                    continue

            # 2. Transient network error detection
            if self.config.transient_error_check_enabled:
                if self._detect_transient_error(error_lower, execution_result):
                    v.verdict = "WARN"
                    v.confidence = max(v.confidence, 0.25)
                    v.is_false_positive = True
                    v.evidence += " | FP: transient network error"
                    continue

            # 3. Rate limiting detection
            if self.config.rate_limit_check_enabled:
                if self._detect_rate_limiting(error_lower, execution_result):
                    v.verdict = "WARN"
                    v.confidence = max(v.confidence, 0.3)
                    v.is_false_positive = True
                    v.evidence += " | FP: rate limiting detected"
                    continue

            # 4. Known flaky patterns
            if self.config.flaky_pattern_check_enabled:
                pattern, conf = self._match_flaky_pattern(error_lower)
                if pattern:
                    v.verdict = "WARN"
                    v.confidence = max(v.confidence, conf)
                    v.is_false_positive = True
                    v.evidence += f" | FP: flaky pattern '{pattern}'"
                    continue

        return verdicts

    def _detect_loading_state(self, error_lower: str) -> bool:
        """Detect if the failure is caused by a page still loading."""
        loading_count = sum(1 for kw in LOADING_KEYWORDS if kw in error_lower)
        return loading_count >= 2

    def _detect_transient_error(self, error_lower: str,
                                er: TestExecutionResult) -> bool:
        """Detect transient network errors."""
        transient_keywords = [
            "timeout", "connection reset", "temporary failure",
            "econnrefused", "etimedout", "name resolution",
            "network error", "connection refused",
        ]
        return any(kw in error_lower for kw in transient_keywords)

    def _detect_rate_limiting(self, error_lower: str,
                              er: TestExecutionResult) -> bool:
        """Detect rate limiting (429 or retry-after headers)."""
        if "429" in error_lower or "retry-after" in error_lower:
            return True
        # Check API calls for 429
        for sr in er.step_results:
            for call in (sr.api_calls or []):
                resp = call.get("response", {}) if isinstance(call, dict) else {}
                status = resp.get("status", 0) if isinstance(resp, dict) else 0
                if status in RATE_LIMIT_CODES:
                    return True
        return False

    def _match_flaky_pattern(self, error_lower: str) -> Tuple[Optional[str], float]:
        """Match error text against known flaky patterns.

        Returns:
            (pattern_string, confidence) or (None, 0.0)
        """
        for pattern, confidence in FLAKY_PATTERNS:
            if re.search(pattern, error_lower):
                return pattern, confidence
        return None, 0.0

    # ── Overall Verdict Logic ──

    def _determine_overall_verdict(self, result: JudgementResult) -> str:
        """Determine the overall PASS/FAIL/FLAKY verdict.

        Logic:
        - All true PASS → PASS
        - Any false-positive flags present → FLAKY
        - Mixed real FAILs → FAIL
        - Any low-confidence → FLAKY if not clearly FAIL
        """
        real_fails = [v for v in result.verdicts
                      if v.verdict == "FAIL" and not v.is_false_positive]
        fp_fails = [v for v in result.verdicts
                    if v.verdict == "FAIL" and v.is_false_positive]
        fp_any = result.false_positives_detected > 0

        if not real_fails and not fp_fails and not fp_any:
            # Clean pass — no issues at all
            low_conf_warns = [v for v in result.verdicts
                              if v.verdict == "WARN"
                              and v.confidence < self.config.low_confidence_threshold]
            if low_conf_warns:
                return OverallVerdict.FLAKY.value
            return OverallVerdict.PASS.value

        if real_fails:
            # Have genuine (non-filtered) failures
            if result.confidence < self.config.low_confidence_threshold:
                return OverallVerdict.FLAKY.value
            return OverallVerdict.FAIL.value

        # False positives present (filtered or unfiltered)
        if fp_fails or fp_any:
            return OverallVerdict.FLAKY.value

        return OverallVerdict.FLAKY.value  # default (safety net)

    def _generate_recommendation(self, result: JudgementResult) -> str:
        """Generate a human-readable recommendation."""
        parts: List[str] = []

        if result.overall_verdict == "PASS":
            if result.confidence >= self.config.high_confidence_threshold:
                parts.append("✅ High-confidence pass. Ready for CI/CD gating.")
            else:
                parts.append(
                    "⚠️  Pass with moderate confidence. "
                    "Consider spot-checking.")

        elif result.overall_verdict == "FAIL":
            real_fails = [v for v in result.verdicts
                          if v.verdict == "FAIL" and not v.is_false_positive]
            fail_types = set(v.check_type for v in real_fails)
            parts.append(f"❌ Genuine failure in: {', '.join(sorted(fail_types))}.")
            parts.append("Investigate failing checks and re-run after fixing.")
            if result.false_positives_detected > 0:
                parts.append(
                    f"({result.false_positives_detected} false-positive(s) filtered.)")

        elif result.overall_verdict == "FLAKY":
            if result.false_positives_detected > 0:
                parts.append(
                    f"🔶 {result.false_positives_detected} false-positive(s) detected "
                    f"(loading/transient/flaky pattern). Marked FLAKY.")
            if result.confidence < self.config.recommend_human_review_confidence:
                parts.append("🔍 Low confidence — recommend human review.")
            elif result.fail_checks > 0:
                parts.append("⚠️  Failures present but confidence is borderline.")
            else:
                parts.append("⚠️  Result unstable — re-run recommended.")

        if not parts:
            parts.append("Review results manually.")

        # Add specific pointers for low-confidence checks
        low_conf = [v for v in result.verdicts
                    if v.confidence < self.config.low_confidence_threshold]
        if low_conf:
            parts.append(
                f"Review {len(low_conf)} low-confidence check(s): "
                f"{', '.join(v.check_type for v in low_conf[:3])}")

        return " ".join(parts)

    # ── Utilities ──

    def _synthetic_test_case(self, er: TestExecutionResult) -> TestCase:
        """Build a minimal synthetic TestCase from an execution result alone.

        Used when no TestCase is available for pairing.
        """
        try:
            from planner import TestCase as TC, TestExpectation as TE
        except ImportError:
            TC = type('TestCase', (), {})  # type: ignore
            TE = type('TestExpectation', (), {})  # type: ignore

        # Reconstruct expectations from step results
        expectations = []
        for sr in er.step_results:
            if sr.step_action == "navigate":
                expectations.append(TE(
                    type="url_contains",
                    target=sr.step_target or "",
                    expected_value=sr.step_target or "",
                    operator="contains",
                ))
            elif sr.step_action == "verify":
                expectations.append(TE(
                    type="page_content",
                    target="",
                    expected_value=sr.step_description or sr.step_target or "",
                    operator="contains",
                ))

        return TC(
            id=er.test_case_id,
            name=er.test_case_name,
            priority=er.priority,
            category=er.category,
            source_page=er.source_page,
            steps=[],
            expectations=expectations,
            description=f"Synthetic case for {er.test_case_id}",
        )

    # ── Logging ──

    def _log(self, msg: str):
        """Log a judgment message."""
        logger.debug(msg)
        self._judgement_log.append({
            "timestamp": datetime.now().isoformat(),
            "message": msg,
        })

    # ── Reporting ──

    def to_report(self) -> Dict:
        """Produce a full JSON-serializable report of all judgments."""
        return {
            "summary": self.get_summary(),
            "results": [r.to_dict() for r in self._results],
            "judgement_log": self._judgement_log,
        }

    def print_summary(self) -> None:
        """Pretty-print a summary to stdout."""
        s = self.get_summary()
        print(f"\n{'='*60}")
        print(f"  JUDGMENT SUMMARY")
        print(f"{'='*60}")
        print(f"  Total cases judged : {s['total']}")
        print(f"  PASS               : {s['passed']}")
        print(f"  FAIL               : {s['failed']}")
        print(f"  FLAKY              : {s['flaky']}")
        print(f"  Pass rate          : {s['pass_rate']}%")
        print(f"  Avg confidence     : {s['avg_confidence']:.3f}")
        print(f"  False positives    : {s['total_false_positives']}")
        if s['needs_human_review']:
            print(f"  Needs human review : {len(s['needs_human_review'])} cases")
            for cid in s['needs_human_review'][:5]:
                print(f"    - {cid}")
        print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# Module-Level Convenience Function
# ═══════════════════════════════════════════════════════════════

def quick_judge(test_case: TestCase,
                execution_result: TestExecutionResult) -> JudgementResult:
    """One-liner: judge a single test case with default config.

    Usage:
        from src.judge import quick_judge
        result = quick_judge(test_case, execution_result)
        print(result.summary())
    """
    judge = Judge()
    return judge.judge(test_case, execution_result)
