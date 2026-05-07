"""TestSuite 模块 — 用例组装 + 过滤 + 执行

提供:
- Filter: 表达式解析 (P0+form, ~P3, url:/login/)
- DependencyGraph: 用例依赖拓扑排序
- TestSuite: 套件数据类
- SuiteBuilder: 预设模板构建套件
- SuiteRunner: 串行/并行执行

用法:
    from src.suite import SuiteBuilder, SuiteRunner, Filter
    builder = SuiteBuilder()
    suites = builder.build(cases, preset="regression", filter_expr="P0+form")
    runner = SuiteRunner(executor)
    results = runner.run(suites)
"""

from .filter import Filter
from .dependency import DependencyGraph
from .builder import TestSuite, SuiteBuilder
from .runner import SuiteRunner, SuiteResult
