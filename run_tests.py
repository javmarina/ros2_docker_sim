"""
Robust Test Runner for ROS 2 Simulation Launcher.

Features:
- Ensures QT_QPA_PLATFORM=offscreen is set for headless CI execution.
- Invokes pytest with JUnit XML report generation (--junitxml=test-results.xml).
- Authoritatively verifies test pass by inspecting JUnit XML (tests > 0, failures == 0, errors == 0).
- Emits markdown results to GITHUB_STEP_SUMMARY when executing in GitHub Actions.
- Terminates cleanly with os._exit(code) to bypass PySide6/Qt6 C++ unloader faults
  on Windows during Python interpreter shutdown (which causes exit code 127 in CI).
"""

import os
import sys
import xml.etree.ElementTree as ET
import pytest


def run() -> int:
    # Ensure offscreen Qt platform in headless/CI environments
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    report_file = "test-results.xml"
    pytest_args = [
        "test_launcher.py",
        "-v",
        "--tb=short",
        f"--junitxml={report_file}",
    ] + sys.argv[1:]

    print(f"--> [run_tests] Executing pytest: {' '.join(pytest_args)}")
    pytest_ret = pytest.main(pytest_args)

    # Flush streams to guarantee pytest output is fully flushed
    sys.stdout.flush()
    sys.stderr.flush()

    # Parse JUnit XML for authoritative result validation
    if not os.path.exists(report_file):
        print(f"--> [run_tests] Warning: JUnit report {report_file} was not found.")
        return int(pytest_ret) if pytest_ret != 0 else 1

    try:
        tree = ET.parse(report_file)
        root = tree.getroot()
        suite = root.find("testsuite") if root.tag == "testsuites" else root
        if suite is None:
            suite = root

        total_tests = int(suite.attrib.get("tests", 0))
        failures = int(suite.attrib.get("failures", 0))
        errors = int(suite.attrib.get("errors", 0))
        skipped = int(suite.attrib.get("skipped", 0))
        duration = float(suite.attrib.get("time", 0.0))

        print("\n" + "=" * 62)
        print("           TEST SUITE EXECUTION SUMMARY")
        print("=" * 62)
        print(f"  Total tests executed: {total_tests}")
        print(f"  Failures:             {failures}")
        print(f"  Errors:               {errors}")
        print(f"  Skipped:              {skipped}")
        print(f"  Duration:             {duration:.2f}s")
        print(f"  Pytest exit status:   {pytest_ret}")
        print("=" * 62)

        # Output to GitHub Actions Step Summary if available
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            try:
                summary_dir = os.path.dirname(step_summary_path)
                if not summary_dir or os.path.exists(summary_dir):
                    with open(step_summary_path, "a", encoding="utf-8") as f:
                        f.write("### 🧪 ROS 2 Launcher Test Suite\n\n")
                        if failures == 0 and errors == 0 and total_tests > 0:
                            f.write(
                                f"✅ **All {total_tests} unit tests passed successfully!** ({duration:.2f}s)\n\n"
                            )
                        else:
                            f.write(
                                f"❌ **Test suite failed:** {failures} failures, {errors} errors out of {total_tests} tests.\n\n"
                            )

                        f.write("| Test Name | Status | Duration |\n")
                        f.write("| :--- | :---: | :---: |\n")
                        for tc in tree.findall(".//testcase"):
                            name = tc.get("name", "unknown")
                            t_time = tc.get("time", "0.0")
                            has_fail = tc.find("failure") is not None
                            has_err = tc.find("error") is not None
                            if has_fail or has_err:
                                status_badge = "❌ FAILED"
                            else:
                                status_badge = "✅ PASSED"
                            f.write(f"| `{name}` | {status_badge} | {t_time}s |\n")
                        f.write("\n")
            except Exception as sum_err:
                print(f"--> [run_tests] Note: Could not write GITHUB_STEP_SUMMARY: {sum_err}")

        # Deterministic Pass Condition:
        # 1. At least 1 test was collected and run
        # 2. Exactly 0 test failures
        # 3. Exactly 0 test errors
        if total_tests > 0 and failures == 0 and errors == 0:
            print("--> [run_tests] RESULT: ALL TESTS PASSED.")
            return 0
        else:
            print(f"--> [run_tests] RESULT: FAILED ({failures} failures, {errors} errors).")
            return 1

    except Exception as parse_err:
        print(f"--> [run_tests] Error parsing JUnit XML report: {parse_err}")
        return int(pytest_ret) if pytest_ret != 0 else 1


if __name__ == "__main__":
    code = run()
    sys.stdout.flush()
    sys.stderr.flush()
    # Immediate termination prevents PySide6/Qt6 C++ destruction crashes during
    # standard Python interpreter shutdown on Windows runners (which caused exit code 127).
    os._exit(code)
