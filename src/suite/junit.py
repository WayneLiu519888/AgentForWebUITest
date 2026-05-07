"""JUnit XML Report Generator

Generates JUnit-compatible XML from SuiteResult list.
Compatible with GitHub Actions test-reporter, Jenkins, and other CI tools.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List

from .runner import SuiteResult


class JUnitReport:
    """Generate JUnit XML from SuiteResult list.

    Usage:
        results: List[SuiteResult] = runner.run(suites)
        xml_str = JUnitReport.generate(results)
        JUnitReport.write(results, "ci-artifacts/junit.xml")
    """

    @staticmethod
    def generate(results: List[SuiteResult]) -> str:
        """Generate JUnit XML string from a list of SuiteResult.

        Each SuiteResult becomes a <testsuite> element.
        Each TestExecutionResult in case_results becomes a <testcase>.
        FAIL/ERROR statuses produce <failure> or <error> child elements.

        Args:
            results: List of SuiteResult from suite execution.

        Returns:
            Pretty-printed JUnit XML string.
        """
        testsuites = ET.Element("testsuites")

        for result in results:
            failures = result.cases_failed + result.cases_error
            time_sec = f"{result.duration_ms / 1000:.3f}"

            suite = ET.SubElement(
                testsuites,
                "testsuite",
                {
                    "name": result.suite_name,
                    "tests": str(result.cases_total),
                    "failures": str(failures),
                    "errors": str(result.cases_error),
                    "skipped": str(result.cases_skipped),
                    "time": time_sec,
                },
            )

            for case in result.case_results:
                case_id = getattr(case, "test_case_id", "unknown")
                case_name = getattr(case, "test_case_name", case_id)
                name = f"{case_id}: {case_name}"
                case_time = getattr(case, "total_duration_ms", 0) / 1000

                testcase = ET.SubElement(
                    suite,
                    "testcase",
                    {
                        "name": name,
                        "classname": result.suite_name,
                        "time": f"{case_time:.3f}",
                    },
                )

                status = getattr(case, "status", "PASS")
                error_summary = getattr(case, "error_summary", "") or ""

                if status in ("FAIL", "failed"):
                    msg = error_summary[:200] if error_summary else "test failed"
                    failure = ET.SubElement(
                        testcase, "failure", {"message": msg}
                    )
                    failure.text = error_summary
                elif status in ("ERROR", "error"):
                    msg = error_summary[:200] if error_summary else "execution error"
                    error = ET.SubElement(
                        testcase, "error", {"message": msg}
                    )
                    error.text = error_summary
                elif status in ("SKIP", "skipped", "SKIPPED"):
                    ET.SubElement(testcase, "skipped")

        xml_str = ET.tostring(testsuites, encoding="unicode")
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ")

    @staticmethod
    def write(results: List[SuiteResult], path: str) -> str:
        """Write JUnit XML to a file path. Creates parent directories.

        Args:
            results: List of SuiteResult from suite execution.
            path: Output file path (e.g. "ci-artifacts/junit.xml").

        Returns:
            The path that was written to.
        """
        import os

        xml = JUnitReport.generate(results)
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        return path
