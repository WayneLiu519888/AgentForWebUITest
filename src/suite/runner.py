"""SuiteRunner — 套件执行器 (支持串行/并行)

用法:
    from src.suite.runner import SuiteRunner, SuiteResult
    runner = SuiteRunner(executor)
    results = runner.run(suites)

CI 模式:
    runner = SuiteRunner(executor, ci_mode=True)
    results = runner.run(suites)  # 退出码 = 失败数
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

try:
    from .builder import TestSuite
    from .dependency import DependencyGraph
except ImportError:
    from builder import TestSuite
    from dependency import DependencyGraph

logger = logging.getLogger(__name__)


@dataclass
class SuiteResult:
    """套件执行结果"""
    suite_name: str
    cases_total: int = 0
    cases_passed: int = 0
    cases_failed: int = 0
    cases_partial: int = 0
    cases_skipped: int = 0
    cases_error: int = 0
    pass_rate: float = 0.0
    duration_ms: int = 0
    case_results: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    @property
    def passed(self) -> bool:
        return self.cases_failed == 0 and self.cases_error == 0
    
    @property
    def total(self) -> int:
        return self.cases_total
    
    @property
    def failed(self) -> int:
        return self.cases_failed + self.cases_error
    
    def to_dict(self) -> dict:
        return {
            "suite_name": self.suite_name,
            "total": self.cases_total,
            "passed": self.cases_passed,
            "failed": self.cases_failed,
            "partial": self.cases_partial,
            "skipped": self.cases_skipped,
            "error": self.cases_error,
            "pass_rate": round(self.pass_rate, 1),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class SuiteRunner:
    """套件执行器"""
    
    def __init__(self, executor, ci_mode: bool = False, 
                 continue_on_failure: bool = True,
                 max_workers: int = 1):
        """
        Args:
            executor: TestExecutor 实例
            ci_mode: CI模式 (严格退出码)
            continue_on_failure: 失败后继续执行
            max_workers: 并行执行的最大工作线程数
        """
        self.executor = executor
        self.ci_mode = ci_mode
        self.continue_on_failure = continue_on_failure
        self.max_workers = max_workers
    
    def run(self, suites: List[TestSuite], 
            parallel: bool = False) -> List[SuiteResult]:
        """执行所有套件
        
        Args:
            suites: 套件列表
            parallel: 是否并行执行 (独立套件可并发)
        
        Returns:
            SuiteResult 列表
        """
        results = []
        
        # 分离独立和有依赖的套件
        independent = [s for s in suites if not s.dependencies]
        dependent = [s for s in suites if s.dependencies]
        
        # 并行执行独立套件
        if parallel and self.max_workers > 1 and independent:
            results.extend(self._run_parallel(independent))
        else:
            for suite in independent:
                result = self.run_single(suite)
                results.append(result)
                if not result.passed and not self.continue_on_failure:
                    break
        
        # 串行执行有依赖的套件
        for suite in dependent:
            result = self.run_single(suite)
            results.append(result)
            if not result.passed and not self.continue_on_failure:
                break
        
        return results
    
    def run_single(self, suite: TestSuite) -> SuiteResult:
        """执行单个套件
        
        按依赖拓扑排序后串行执行。
        """
        start = time.time()
        result = SuiteResult(suite_name=suite.name, metadata=suite.metadata)
        
        if not suite.cases:
            result.duration_ms = int((time.time() - start) * 1000)
            return result
        
        # 拓扑排序
        try:
            case_ids = [getattr(c, "id", str(i)) for i, c in enumerate(suite.cases)]
            graph = DependencyGraph(case_ids, suite.dependencies)
            order = graph.resolve()
            id_to_case = {}
            for i, c in enumerate(suite.cases):
                cid = getattr(c, "id", str(i))
                id_to_case[cid] = c
            ordered_cases = [id_to_case[oid] for oid in order if oid in id_to_case]
        except Exception as e:
            logger.warning("依赖解析失败，使用原始顺序: %s", e)
            ordered_cases = suite.cases
        
        # 执行
        result.cases_total = len(ordered_cases)
        passed_ids = set()
        
        for case in ordered_cases:
            cid = getattr(case, "id", "")
            
            # 依赖检查: 前置用例必须全部通过
            if not graph.can_execute(cid, passed_ids):
                result.cases_skipped += 1
                continue
            
            try:
                exec_result = self.executor.execute_test_case(case)
                result.case_results.append(exec_result)
                
                status = getattr(exec_result, "status", "unknown")
                if status == "passed":
                    result.cases_passed += 1
                    if cid:
                        passed_ids.add(cid)
                elif status == "partial":
                    result.cases_partial += 1
                    if cid:
                        passed_ids.add(cid)  # partial也视为依赖满足
                elif status == "failed":
                    result.cases_failed += 1
                elif status == "error":
                    result.cases_error += 1
                else:
                    result.cases_passed += 1
                    if cid:
                        passed_ids.add(cid)
                        
            except Exception as e:
                logger.error("用例 %s 执行异常: %s", cid, e)
                result.cases_error += 1
            
            # 失败立即停止
            if result.cases_failed > 0 and not self.continue_on_failure:
                break
        
        result.duration_ms = int((time.time() - start) * 1000)
        if result.cases_total > 0:
            result.pass_rate = (result.cases_passed / result.cases_total) * 100
        
        return result
    
    def _run_parallel(self, suites: List[TestSuite]) -> List[SuiteResult]:
        """并行执行独立套件"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(suites))) as pool:
            futures = {pool.submit(self.run_single, s): s.name for s in suites}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error("套件 %s 执行异常: %s", futures[future], e)
        return results
    
    def get_ci_exit_code(self, results: List[SuiteResult]) -> int:
        """计算CI退出码: 0=全绿, N=N个失败 (max 255)"""
        failed = sum(r.failed for r in results)
        if self.ci_mode:
            return min(failed, 255)
        return 0
    
    def get_summary(self, results: List[SuiteResult]) -> dict:
        """汇总所有套件结果"""
        total = sum(r.cases_total for r in results)
        passed = sum(r.cases_passed for r in results)
        failed = sum(r.cases_failed for r in results)
        partial = sum(r.cases_partial for r in results)
        skipped = sum(r.cases_skipped for r in results)
        errors = sum(r.cases_error for r in results)
        
        return {
            "suites": len(results),
            "total": total,
            "passed": passed,
            "failed": failed,
            "partial": partial,
            "skipped": skipped,
            "error": errors,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "duration_ms": sum(r.duration_ms for r in results),
        }
    
    def print_summary(self, results: List[SuiteResult]):
        """打印执行摘要"""
        s = self.get_summary(results)
        
        print()
        print("=" * 60)
        print("  TestSuite 执行摘要")
        print("=" * 60)
        for r in results:
            icon = "✅" if r.passed else "❌"
            print(f"  {icon} {r.suite_name}: {r.cases_passed}/{r.cases_total} "
                  f"({r.pass_rate:.0f}%) — {r.duration_ms}ms")
        
        print(f"  {'─' * 56}")
        print(f"  总计: {s['total']} 用例 | "
              f"✅ {s['passed']} passed | "
              f"❌ {s['failed']} failed | "
              f"⚠️ {s['partial']} partial | "
              f"⏭️ {s['skipped']} skipped")
        print(f"  通过率: {s['pass_rate']}%")
        print("=" * 60)
