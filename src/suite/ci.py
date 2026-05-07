"""CI Mode Runner for AgentForWebUITest

Provides CI-optimized suite execution with:
- Exit code based on failure count (min(failed, 255))
- JUnit XML artifact generation (ci-artifacts/junit.xml)
- Verbose summary output
"""

import sys
from pathlib import Path
from typing import List, Optional

from .runner import SuiteResult
from .junit import JUnitReport


class CIRunner:
    """CI mode runner with exit code control and artifact generation.

    Usage:
        from src.agent import WebUITestAgent
        from src.suite.ci import CIRunner

        agent = WebUITestAgent()
        runner = CIRunner(artifact_dir="ci-artifacts", verbose=True)
        exit_code = runner.run_and_report(agent, "https://example.com", preset="smoke")
        sys.exit(exit_code)
    """

    def __init__(self, artifact_dir: str = "ci-artifacts", verbose: bool = True):
        """Initialize CI runner.

        Args:
            artifact_dir: Directory for CI artifacts (junit.xml).
            verbose: Print progress and summary to stdout.
        """
        self.artifact_dir = Path(artifact_dir)
        self.verbose = verbose

    def run_and_report(
        self,
        agent,
        url: str,
        preset: str = "regression",
        filter_expr: Optional[str] = None,
        split: bool = False,
    ) -> int:
        """Run suite in CI mode and return an exit code (0-255).

        Pipeline:
          1. Explore + plan (generate test cases without executing them).
          2. Build suites via SuiteBuilder.
          3. Execute suites via SuiteRunner (ci_mode=True).
          4. Archive JUnit XML to artifact_dir.
          5. Compute exit code = min(total_failures, 255).

        Args:
            agent: WebUITestAgent instance.
            url: Target URL.
            preset: Suite preset (smoke/critical/regression/full).
            filter_expr: Optional filter expression.
            split: Split suites by category.

        Returns:
            Exit code: 0 on success, failures count (capped at 255) on failure.
        """
        # ── Step 1: Explore + Plan (no execution) ──
        if self.verbose:
            print(f"[CI] Exploring {url} ...")

        result = agent.run(f"测试 {url}", execute=False)
        test_cases = result.get("test_cases", [])

        if not test_cases:
            if self.verbose:
                print("[CI] No test cases generated, exiting with code 0")
            return 0

        if self.verbose:
            print(f"[CI] Generated {len(test_cases)} test case(s)")

        # ── Step 2: Build suites ──
        from .builder import SuiteBuilder

        builder = SuiteBuilder()
        suites = builder.build(
            test_cases,
            preset=preset,
            filter_expr=filter_expr,
            split_by_category=split,
        )

        if self.verbose:
            total_in_suites = sum(len(s.cases) for s in suites)
            print(f"[CI] Built {len(suites)} suite(s) containing {total_in_suites} case(s)")

        # ── Step 3: Set up browser (if configured) ──
        browser = None
        exec_cfg = agent.config.get("executor", {})
        if exec_cfg.get("use_browser", False):
            from datetime import datetime

            try:
                from src.browser import AgentBrowser, BrowserConfig

                browser_config = BrowserConfig(
                    headless=True,
                    session_name=f"ci-suite-{datetime.now().strftime('%H%M%S')}",
                )
                browser = AgentBrowser(browser_config)
            except Exception:
                pass  # Browser not available, continue without

        # ── Step 4: Execute ──
        from src.executor import TestExecutor, ExecutionConfig

        executor_config = ExecutionConfig(
            screenshot_on_step=exec_cfg.get("screenshot_on_step", True),
            screenshot_on_fail=exec_cfg.get("screenshot_on_fail", True),
            screenshot_dir=exec_cfg.get("screenshot_dir", "reports/screenshots"),
            max_retries_per_step=exec_cfg.get("max_retries_per_step", 2),
            enable_healing=exec_cfg.get("enable_healing", True),
        )
        executor = TestExecutor(
            browser=browser,
            knowledge_graph=agent.knowledge_graph,
            config=executor_config,
        )

        from .runner import SuiteRunner

        runner = SuiteRunner(
            executor,
            ci_mode=True,
            continue_on_failure=True,
            max_workers=agent.config.get("suite", {}).get("max_workers", 1),
        )

        if self.verbose:
            print(f"[CI] Executing {len(suites)} suite(s) ...")

        suite_results: List[SuiteResult] = runner.run(
            suites,
            parallel=agent.config.get("suite", {}).get("parallel", False),
        )

        # ── Cleanup browser ──
        if browser:
            try:
                browser.close()
            except Exception:
                pass

        # ── Step 5: Archive artifacts ──
        self._archive_artifacts(suite_results)

        # ── Step 6: Compute exit code ──
        total_failed = sum(r.cases_failed + r.cases_error for r in suite_results)
        exit_code = min(total_failed, 255)

        if self.verbose:
            self._print_summary(suite_results, exit_code)

        return exit_code

    def _archive_artifacts(self, results: List[SuiteResult]) -> str:
        """Write JUnit XML artifact to artifact_dir/junit.xml."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        junit_path = self.artifact_dir / "junit.xml"
        JUnitReport.write(results, str(junit_path))
        if self.verbose:
            print(f"[CI] JUnit report written to {junit_path}")
        return str(junit_path)

    def _print_summary(self, results: List[SuiteResult], exit_code: int) -> None:
        """Print CI summary table."""
        total = sum(r.cases_total for r in results)
        passed = sum(r.cases_passed for r in results)
        failed = sum(r.cases_failed + r.cases_error for r in results)

        print()
        print("=" * 60)
        print("  CI Suite Summary")
        print("=" * 60)
        for r in results:
            icon = "✅" if r.passed else "❌"
            r_failed = r.cases_failed + r.cases_error
            print(
                f"  {icon} {r.suite_name}: "
                f"{r.cases_passed}/{r.cases_total} passed, "
                f"{r_failed} failed ({r.pass_rate:.1f}%)"
            )
        print("-" * 60)
        print(f"  Total: {total} tests, {passed} passed, {failed} failed")
        print(f"  Exit Code: {exit_code}")
        print("=" * 60)
