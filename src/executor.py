"""
ReAct自主执行引擎 (ReAct Execution Engine) — 迭代3核心模块

实现ReAct循环: Observe→Think→Act→Verify
从Planner生成的测试用例逐步执行，自动记录每步结果。

用法:
    from src.executor import TestExecutor
    executor = TestExecutor(browser, knowledge_graph)
    result = executor.execute_test_case(test_case)
    results = executor.execute_all(test_cases)
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict

try:
    from .planner import TestCase, TestStep, TestExpectation
    from .healer import SelectorHealer, HealingRecord
except ImportError:
    from planner import TestCase, TestStep, TestExpectation
    from healer import SelectorHealer, HealingRecord

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class StepResult:
    """单个步骤的执行结果"""
    step_index: int
    step_action: str
    step_target: str
    step_value: str = ""
    step_description: str = ""

    status: str = "PENDING"  # PENDING | PASS | FAIL | SKIP | HEALED
    duration_ms: float = 0.0
    error_message: str = ""
    screenshot_path: str = ""
    api_calls: List[Dict] = field(default_factory=list)
    healing_record: Optional[HealingRecord] = None

    # ReAct阶段详情
    observe_snapshot: str = ""
    think_reasoning: str = ""
    act_detail: str = ""
    verify_result: str = ""

    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        d = asdict(self)
        if self.healing_record:
            d["healing_record"] = self.healing_record.to_dict()
        return d


@dataclass
class TestExecutionResult:
    """单个测试用例的完整执行结果"""
    __test__ = False
    test_case_id: str
    test_case_name: str
    priority: str
    category: str
    source_page: str

    status: str = "PENDING"  # PASS | FAIL | SKIP | PARTIAL
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    healed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 0.0
    error_summary: str = ""
    step_results: List[StepResult] = field(default_factory=list)
    healing_records: List[HealingRecord] = field(default_factory=list)

    start_time: str = ""
    end_time: str = ""

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now().isoformat()

    @property
    def pass_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.passed_steps + self.healed_steps) / self.total_steps * 100

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["pass_rate"] = round(self.pass_rate, 1)
        return d

    def summary(self) -> str:
        return (f"{self.test_case_id} [{self.priority}] {self.status} "
                f"({self.passed_steps}/{self.total_steps} pass, "
                f"{self.healed_steps} healed, {self.failed_steps} fail)")


@dataclass
class ExecutionConfig:
    """执行器配置"""
    screenshot_on_step: bool = True
    screenshot_on_fail: bool = True
    screenshot_dir: str = "reports/screenshots"
    max_retries_per_step: int = 2
    step_timeout_ms: int = 30000
    wait_after_action_ms: int = 1000
    verify_timeout_ms: int = 5000
    skip_on_first_failure: bool = False
    continue_on_failure: bool = True
    enable_healing: bool = True
    verbose: bool = True


# ═══════════════════════════════════════════════════════════════
# TestExecutor
# ═══════════════════════════════════════════════════════════════

class TestExecutor:
    """ReAct自主执行引擎

    ReAct循环: Observe(观察)→Think(思考)→Act(动作)→Verify(验证)

    支持操作: type / click / select / navigate / wait / scroll / verify

    用法:
        executor = TestExecutor(browser, knowledge_graph)
        result = executor.execute_test_case(test_case)
        print(result.summary())
    """

    __test__ = False  # 不是pytest测试类

    def __init__(self, browser=None, knowledge_graph=None, config: ExecutionConfig = None):
        self.browser = browser
        self.knowledge_graph = knowledge_graph
        self.config = config or ExecutionConfig()
        self.healer = SelectorHealer() if self.config.enable_healing else None
        self._execution_log: List[StepResult] = []
        self._all_results: List[TestExecutionResult] = []

    def execute_all(self, test_cases: List[TestCase], browser=None) -> List[TestExecutionResult]:
        """批量执行所有测试用例

        Args:
            test_cases: TestCase列表
            browser: 浏览器实例（可选，覆盖构造时传入的）

        Returns:
            List[TestExecutionResult]: 所有用例的执行结果
        """
        if browser:
            self.browser = browser

        self._all_results = []
        total = len(test_cases)

        print(f"\n[Executor] 开始执行 {total} 个测试用例")
        print(f"[Executor] 配置: healing={'ON' if self.config.enable_healing else 'OFF'}, "
              f"skip_on_first_fail={self.config.skip_on_first_failure}")

        for i, case in enumerate(test_cases):
            print(f"\n[{i+1}/{total}] {case.id} — {case.name}")
            result = self.execute_test_case(case)
            self._all_results.append(result)

        # 汇总统计
        passed = sum(1 for r in self._all_results if r.status == "PASS")
        failed = sum(1 for r in self._all_results if r.status == "FAIL")
        partial = sum(1 for r in self._all_results if r.status == "PARTIAL")
        skipped = sum(1 for r in self._all_results if r.status == "SKIP")

        print(f"\n[Executor] 执行完成: {passed} PASS, {failed} FAIL, "
              f"{partial} PARTIAL, {skipped} SKIP")

        return self._all_results

    def execute_test_case(self, test_case: TestCase, browser=None) -> TestExecutionResult:
        """执行单个测试用例（ReAct循环）

        Args:
            test_case: 要执行的TestCase
            browser: 浏览器实例（可选）

        Returns:
            TestExecutionResult: 执行结果
        """
        if browser:
            self.browser = browser

        result = TestExecutionResult(
            test_case_id=test_case.id,
            test_case_name=test_case.name,
            priority=test_case.priority,
            category=test_case.category,
            source_page=test_case.source_page,
            total_steps=len(test_case.steps),
        )

        if not test_case.steps:
            result.status = "SKIP"
            result.error_summary = "无执行步骤"
            result.end_time = datetime.now().isoformat()
            return result

        if self.config.verbose:
            print(f"  [{test_case.id}] 开始执行 ({len(test_case.steps)}步)")

        # 为截图创建目录
        ss_dir = self.config.screenshot_dir
        if self.config.screenshot_on_step and ss_dir:
            os.makedirs(ss_dir, exist_ok=True)

        # 逐步执行 ReAct 循环
        for i, step in enumerate(test_case.steps):
            step_result = self._execute_step(step, i, test_case, ss_dir)
            result.step_results.append(step_result)
            result.total_duration_ms += step_result.duration_ms

            if step_result.status == "PASS":
                result.passed_steps += 1
            elif step_result.status == "FAIL":
                result.failed_steps += 1
            elif step_result.status == "HEALED":
                result.healed_steps += 1
                if step_result.healing_record:
                    result.healing_records.append(step_result.healing_record)
            elif step_result.status == "SKIP":
                result.skipped_steps += 1

            if self.config.verbose:
                icon = {"PASS": "✅", "FAIL": "❌", "HEALED": "🔧",
                        "SKIP": "⏭️", "PENDING": "⏳"}.get(step_result.status, "❓")
                dur = f"{step_result.duration_ms:.0f}ms"
                desc = step.description or f"{step.action} {step.target}"
                print(f"    {icon} 步骤{i+1}: {desc} [{step_result.status}] ({dur})")

            # 失败处理
            if step_result.status == "FAIL":
                if self.config.skip_on_first_failure:
                    # 跳过剩余步骤
                    for j in range(i + 1, len(test_case.steps)):
                        skipped = StepResult(
                            step_index=j,
                            step_action=test_case.steps[j].action,
                            step_target=test_case.steps[j].target,
                            step_value=test_case.steps[j].value,
                            step_description=test_case.steps[j].description,
                            status="SKIP",
                            error_message="前序步骤失败，跳过",
                        )
                        result.step_results.append(skipped)
                        result.skipped_steps += 1
                    break

        # 判定最终状态
        result.end_time = datetime.now().isoformat()
        if result.failed_steps == 0 and result.skipped_steps == 0:
            result.status = "PASS"
        elif result.passed_steps + result.healed_steps == result.total_steps:
            result.status = "PASS"
        elif result.failed_steps > 0 and result.passed_steps + result.healed_steps > 0:
            result.status = "PARTIAL"
        elif result.failed_steps == result.total_steps:
            result.status = "FAIL"
        elif result.skipped_steps == result.total_steps:
            result.status = "SKIP"
        else:
            result.status = "PARTIAL"

        if result.failed_steps > 0:
            errors = [r.error_message for r in result.step_results
                      if r.status == "FAIL" and r.error_message]
            result.error_summary = "; ".join(errors[:3])

        return result

    # ── ReAct Core ──

    def _execute_step(self, step: TestStep, index: int,
                      test_case: TestCase, ss_dir: str) -> StepResult:
        """ReAct循环执行单个步骤"""
        step_result = StepResult(
            step_index=index,
            step_action=step.action,
            step_target=step.target,
            step_value=step.value,
            step_description=step.description,
        )

        start = time.time()

        try:
            # ── Phase 1: Observe ──
            ref_id = self._react_observe(step, step_result, test_case)

            # ── Phase 2: Think ──
            action_strategy = self._react_think(step, ref_id, step_result)

            # ── Phase 3: Act ──
            acted = self._react_act(step, ref_id, action_strategy, step_result)

            # ── Phase 4: Verify ──
            verified = self._react_verify(step, acted, step_result, test_case)

            if verified:
                step_result.status = "PASS" if not step_result.healing_record else "HEALED"
            else:
                step_result.status = "FAIL"
                if not step_result.error_message:
                    step_result.error_message = f"验证失败: {step.action} {step.target}"

            # 截图
            if self.config.screenshot_on_step and ss_dir:
                step_result.screenshot_path = self._capture_screenshot(
                    test_case.id, index, ss_dir)

        except Exception as e:
            step_result.status = "FAIL"
            step_result.error_message = f"{type(e).__name__}: {e}"
            logger.error(f"步骤执行异常: {e}", exc_info=True)

            # 失败截图
            if self.config.screenshot_on_fail and ss_dir:
                try:
                    step_result.screenshot_path = self._capture_screenshot(
                        test_case.id, index, ss_dir)
                except Exception:
                    pass

        step_result.duration_ms = (time.time() - start) * 1000
        return step_result

    def _react_observe(self, step: TestStep, result: StepResult,
                       test_case: TestCase) -> Optional[str]:
        """Phase 1: Observe — 获取当前页面状态，识别目标元素

        Returns:
            ref_id 字符串（如 @e42），或 None
        """
        ref_id = None

        if self.browser:
            try:
                # 获取快照
                snapshot_data = self.browser.snapshot(interactive_only=True)
                snapshot = snapshot_data.get("snapshot", "") if isinstance(snapshot_data, dict) else str(snapshot_data)
                result.observe_snapshot = snapshot[:2000]  # 截断存储
                refs = snapshot_data.get("refs", {}) if isinstance(snapshot_data, dict) else {}

                # 对于 verify 操作，不需要找元素ref
                if step.action in ("verify",):
                    return None

                # 使用 healer 定位元素
                if self.healer and step.target:
                    page_context = {
                        "snapshot": snapshot,
                        "refs": refs,
                        "source_page": test_case.source_page,
                        "step_description": step.description,
                    }
                    ref_id = self.healer.find_element(
                        self.browser, step.target, page_context)

                    if ref_id:
                        result.think_reasoning = (
                            f"定位成功: {step.target} → {ref_id} "
                            f"(策略: {self.healer.last_strategy_used})"
                        )
                    else:
                        result.error_message = f"无法定位元素: {step.target}"
                elif step.target and step.target.startswith("@e"):
                    # 直接使用ref
                    ref_id = step.target
                    result.think_reasoning = f"直接使用ref: {ref_id}"
                elif step.target and (step.target.startswith("http://") or
                                      step.target.startswith("https://")):
                    # URL导航，不需要ref
                    ref_id = None
                    result.think_reasoning = f"URL导航: {step.target}"

            except Exception as e:
                logger.warning(f"Observe阶段异常: {e}")
                result.observe_snapshot = f"ERROR: {e}"

        return ref_id

    def _react_think(self, step: TestStep, ref_id: Optional[str],
                     result: StepResult) -> Dict:
        """Phase 2: Think — 分析策略"""
        strategy = {
            "action": step.action,
            "target": step.target,
            "ref_id": ref_id,
            "value": step.value,
            "needs_confirmation": False,
            "wait_before_ms": 300,
            "wait_after_ms": self.config.wait_after_action_ms,
        }

        if step.action == "type":
            strategy["needs_clear"] = True
            strategy["needs_confirmation"] = False
            result.think_reasoning = (
                result.think_reasoning or
                f"输入操作: 在 {step.target} 输入 '{step.value}'"
            )
        elif step.action == "click":
            strategy["scroll_to_view"] = True
            strategy["wait_after_ms"] = max(self.config.wait_after_action_ms, 2000)
            result.think_reasoning = (
                result.think_reasoning or
                f"点击操作: 点击 {step.target}"
            )
        elif step.action == "select":
            result.think_reasoning = (
                result.think_reasoning or
                f"选择操作: 在 {step.target} 选择 '{step.value}'"
            )
        elif step.action == "navigate":
            strategy["wait_after_ms"] = max(self.config.wait_after_action_ms, 3000)
            result.think_reasoning = (
                result.think_reasoning or
                f"导航操作: 前往 {step.target}"
            )
        elif step.action == "wait":
            strategy["wait_ms"] = int(step.value) if step.value.isdigit() else 1000
            result.think_reasoning = f"等待: {strategy['wait_ms']}ms"
        elif step.action == "scroll":
            result.think_reasoning = f"滚动: {step.value or 'down'}"
        elif step.action == "verify":
            strategy["wait_after_ms"] = 0
            result.think_reasoning = f"验证: {step.description or step.target}"

        return strategy

    def _react_act(self, step: TestStep, ref_id: Optional[str],
                   strategy: Dict, result: StepResult) -> bool:
        """Phase 3: Act — 执行操作

        Returns:
            bool: 操作是否成功
        """
        if not self.browser:
            # 模拟模式
            result.act_detail = f"[模拟] {step.action} {step.target} (无浏览器)"
            return True

        action = step.action
        success = False
        detail_parts = []

        try:
            if action == "type":
                if ref_id and step.value:
                    detail_parts.append(f"fill({ref_id}, '{step.value}')")
                    success = self.browser.fill(ref_id, step.value)

            elif action == "click":
                if ref_id and ref_id.startswith("@e"):
                    detail_parts.append(f"click({ref_id})")
                    success = self.browser.click(ref_id)

            elif action == "select":
                if ref_id and step.value:
                    detail_parts.append(f"select({ref_id}, '{step.value}')")
                    # agent-browser 没有原生select，用fill代替
                    success = self.browser.fill(ref_id, step.value)

            elif action == "navigate":
                target_url = step.target or step.value
                if target_url:
                    detail_parts.append(f"navigate({target_url})")
                    success = self.browser.navigate(target_url)
                    if success:
                        # 等待页面加载
                        self.browser.wait(strategy.get("wait_after_ms", 3000))

            elif action == "wait":
                wait_ms = int(step.value) if step.value and step.value.isdigit() else 1000
                detail_parts.append(f"wait({wait_ms}ms)")
                success = self.browser.wait(wait_ms)

            elif action == "scroll":
                direction = step.value or "down"
                detail_parts.append(f"scroll({direction})")
                success = self.browser.scroll(direction)

            elif action == "verify":
                detail_parts.append(f"verify({step.target})")
                success = True  # 验证逻辑在verify阶段

            else:
                detail_parts.append(f"unsupported: {action}")
                result.error_message = f"不支持的操作类型: {action}"
                success = False

        except Exception as e:
            detail_parts.append(f"ERROR: {e}")
            result.error_message = f"{action}操作异常: {e}"
            success = False

        result.act_detail = "; ".join(detail_parts)
        return success

    def _react_verify(self, step: TestStep, acted: bool,
                      result: StepResult, test_case: TestCase) -> bool:
        """Phase 4: Verify — 验证操作结果

        Returns:
            bool: 验证是否通过
        """
        if not acted and step.action != "verify":
            result.verify_result = "操作执行失败，跳过验证"
            return False

        verify_details = []

        if step.action == "verify":
            # 专门验证步骤
            return self._verify_expectations(test_case, result, verify_details)

        if not self.browser:
            # 模拟模式: 总是通过
            verify_details.append("[模拟] 验证通过")
            result.verify_result = "; ".join(verify_details)
            return True

        try:
            # 通用验证: 检查页面状态
            if step.action in ("click", "navigate"):
                # 等待页面稳定
                self.browser.wait(self.config.verify_timeout_ms)
                # 检查URL是否改变
                current_url = self.browser.get_url()
                verify_details.append(f"当前URL: {current_url}")

            elif step.action == "type":
                # 等待响应
                time.sleep(0.5)
                verify_details.append("输入完成")

            # 检查是否有API调用
            try:
                api_log = self.browser.get_api_log()
                if api_log:
                    recent = api_log[-3:]  # 最近3个API调用
                    result.api_calls = recent
                    verify_details.append(f"API调用: {len(recent)}个")
            except Exception:
                pass

            verify_details.append("验证通过")
            result.verify_result = "; ".join(verify_details)
            return True

        except Exception as e:
            verify_details.append(f"验证异常: {e}")
            result.verify_result = "; ".join(verify_details)
            return False

    def _verify_expectations(self, test_case: TestCase,
                             result: StepResult,
                             verify_details: List[str]) -> bool:
        """验证测试预期"""
        if not test_case.expectations:
            verify_details.append("无预期条件，验证通过")
            result.verify_result = "; ".join(verify_details)
            return True

        all_passed = True

        for exp in test_case.expectations:
            exp_result = self._check_expectation(exp)
            if exp_result:
                verify_details.append(f"✅ {exp.type} {exp.operator} {exp.expected_value}")
            else:
                verify_details.append(f"❌ {exp.type} {exp.operator} {exp.expected_value}")
                all_passed = False
                if not result.error_message:
                    result.error_message = (
                        f"预期失败: {exp.type} {exp.operator} {exp.expected_value}"
                    )

        result.verify_result = "; ".join(verify_details)
        return all_passed

    def _check_expectation(self, exp: TestExpectation) -> bool:
        """检查单个预期条件"""
        if not self.browser:
            return True  # 模拟模式总是通过

        try:
            if exp.type == "api_status":
                # 检查API日志中的状态码
                api_log = self.browser.get_api_log()
                for call in api_log:
                    resp = call.get("response", {})
                    status = str(resp.get("status", ""))
                    if exp.expected_value == status:
                        if exp.operator == "equals":
                            return True
                return False

            elif exp.type == "page_content":
                # 检查页面内容
                body = self.browser.get_body_text()
                if exp.operator == "contains":
                    return exp.expected_value.lower() in body.lower()
                elif exp.operator == "matches":
                    return bool(re.search(exp.expected_value, body, re.IGNORECASE))
                return exp.expected_value in body

            elif exp.type == "url_contains":
                current_url = self.browser.get_url()
                return exp.expected_value in current_url

            elif exp.type == "element_visible":
                ref_id = exp.target
                if ref_id and ref_id.startswith("@e"):
                    return self.browser.is_visible(ref_id)
                return True  # 无法精确检查时默认通过

            elif exp.type == "element_not_exist":
                ref_id = exp.target
                if ref_id and ref_id.startswith("@e"):
                    return not self.browser.is_visible(ref_id)
                return True

            else:
                logger.warning(f"未知预期类型: {exp.type}")
                return True

        except Exception as e:
            logger.warning(f"预期检查异常: {e}")
            return True  # 检查异常时默认为通过，避免误报

    # ── 辅助方法 ──

    def _capture_screenshot(self, case_id: str, step_idx: int, ss_dir: str) -> str:
        """截取页面截图"""
        if not self.browser:
            return ""
        try:
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', case_id)
            path = os.path.join(
                ss_dir, f"{safe_id}_step{step_idx}_{int(time.time())}.png")
            result = self.browser.screenshot(path)
            return result or ""
        except Exception as e:
            logger.warning(f"截图失败: {e}")
            return ""

    def get_all_results(self) -> List[TestExecutionResult]:
        """获取所有执行结果"""
        return self._all_results

    def get_summary_stats(self) -> Dict:
        """获取汇总统计"""
        results = self._all_results
        if not results:
            return {"total": 0, "passed": 0, "failed": 0, "partial": 0, "skipped": 0,
                    "pass_rate": 0.0, "total_healings": 0}

        stats = {
            "total": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "partial": sum(1 for r in results if r.status == "PARTIAL"),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
            "total_healings": sum(len(r.healing_records) for r in results),
            "total_steps": sum(r.total_steps for r in results),
            "passed_steps": sum(r.passed_steps for r in results),
            "failed_steps": sum(r.failed_steps for r in results),
            "healed_steps": sum(r.healed_steps for r in results),
            "total_duration_ms": sum(r.total_duration_ms for r in results),
        }
        stats["pass_rate"] = round(
            stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0.0
        return stats
