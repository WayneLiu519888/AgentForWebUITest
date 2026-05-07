"""SuiteBuilder — 从用例列表构建测试套件

预置模板:
  smoke        P0, 最多10个
  critical     P0+P1
  regression   P0+P1+P2, 最多50个
  full         P0+P1+P2+P3
  api          仅API用例
  form         仅表单用例
  ui           表单+按钮+链接+页面 (非API)
  a11y         页面用例 (含accessible标签)

用法:
    from src.suite.builder import TestSuite, SuiteBuilder
    builder = SuiteBuilder()
    suites = builder.build(cases, preset="regression", filter_expr="P0+form")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .filter import Filter
from .dependency import DependencyGraph


@dataclass
class TestSuite:
    """测试套件"""
    name: str
    cases: list = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    parallel: bool = False
    metadata: dict = field(default_factory=dict)
    
    @property
    def total(self) -> int:
        return len(self.cases)
    
    @property
    def priorities(self) -> dict:
        counts = {}
        for c in self.cases:
            p = getattr(c, "priority", "?")
            counts[p] = counts.get(p, 0) + 1
        return counts
    
    @property
    def categories(self) -> dict:
        counts = {}
        for c in self.cases:
            cat = getattr(c, "category", "?")
            counts[cat] = counts.get(cat, 0) + 1
        return counts
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total": self.total,
            "priorities": self.priorities,
            "categories": self.categories,
            "parallel": self.parallel,
            "case_ids": [getattr(c, "id", str(i)) for i, c in enumerate(self.cases)],
            "metadata": self.metadata,
        }


class SuiteBuilder:
    """套件构建器
    
    预置模板 + 自定义过滤 = 灵活套件组装
    """
    
    PRESETS = {
        "smoke": {
            "filter_expr": "P0",
            "max_cases": 10,
            "description": "冒烟测试: P0 核心流程，最多10个"
        },
        "critical": {
            "filter_expr": "P0+P1",
            "description": "关键测试: P0 + P1"
        },
        "regression": {
            "filter_expr": "P0+P1+P2",
            "max_cases": 50,
            "description": "回归测试: P0/P1/P2，最多50个"
        },
        "full": {
            "filter_expr": "",
            "description": "全量测试: 所有优先级"
        },
        "api": {
            "filter_expr": "api",
            "description": "API测试: 所有API端点用例"
        },
        "form": {
            "filter_expr": "form",
            "description": "表单测试: 所有表单用例"
        },
        "ui": {
            "filter_expr": "form+button+link+page",
            "description": "UI测试: 非API用例"
        },
    }
    
    def build(self, cases: list,
              preset: str = None,
              filter_expr: str = None,
              split_by_category: bool = False,
              dependencies: Dict[str, List[str]] = None) -> List[TestSuite]:
        """从用例列表构建套件
        
        Args:
            cases: 用例列表
            preset: 预置模板名 (smoke/critical/regression/full/api/form/ui)
            filter_expr: 额外的过滤表达式 (与preset叠加)
            split_by_category: 是否按类别拆分为多个套件
            dependencies: 用例依赖声明 {case_id: [前置id, ...]}
        
        Returns:
            List[TestSuite]
        """
        # 1. 应用预设
        preset_cfg = self.PRESETS.get(preset, {}) if preset else {}
        base_expr = preset_cfg.get("filter_expr", "")
        max_cases = preset_cfg.get("max_cases", 0)
        description = preset_cfg.get("description", "")
        
        # 2. 合并过滤: preset + 用户 filter_expr
        combined_expr = base_expr
        if filter_expr:
            combined_expr = f"{base_expr}+{filter_expr}" if base_expr else filter_expr
        
        # 3. 创建过滤器
        f = Filter.parse(combined_expr, max_cases=max_cases)
        
        # 4. 过滤用例
        matched = f.apply(cases)
        
        if not matched:
            return [TestSuite(name=preset or "empty", cases=[], metadata={"filter": str(f)})]
        
        # 5. 单套件 vs 按类别拆分
        if not split_by_category:
            suite = TestSuite(
                name=preset or "custom",
                cases=matched,
                dependencies=dependencies or self._infer_dependencies(matched),
                metadata={"filter": str(f), "preset": preset, "description": description}
            )
            return [suite]
        
        # 按类别拆分
        from collections import defaultdict
        cat_cases = defaultdict(list)
        for c in matched:
            cat_cases[getattr(c, "category", "other")].append(c)
        
        suites = []
        for cat, cat_list in sorted(cat_cases.items()):
            suites.append(TestSuite(
                name=f"{preset or 'custom'}-{cat}",
                cases=cat_list,
                dependencies=self._infer_dependencies(cat_list),
                metadata={"filter": str(f), "preset": preset, "category": cat}
            ))
        return suites
    
    def _infer_dependencies(self, cases: list) -> Dict[str, List[str]]:
        """从用例属性推断依赖 (基于 source_page 和 name 模式)"""
        deps = {}
        # 如果用例自带 dependencies 属性，使用它们
        for c in cases:
            cid = getattr(c, "id", "")
            if not cid:
                continue
            builtin = getattr(c, "dependencies", None)
            if builtin:
                deps[cid] = builtin
        return deps
    
    def get_resolved_order(self, cases: list, 
                           dependencies: Dict[str, List[str]] = None) -> List:
        """获取拓扑排序后的用例顺序"""
        deps = dependencies or self._infer_dependencies(cases)
        case_ids = [getattr(c, "id", str(i)) for i, c in enumerate(cases)]
        
        try:
            graph = DependencyGraph(case_ids, deps)
            order = graph.resolve()
            # 映射回实际case对象
            id_to_case = {}
            for i, c in enumerate(cases):
                cid = getattr(c, "id", str(i))
                id_to_case[cid] = c
            return [id_to_case[oid] for oid in order if oid in id_to_case]
        except Exception:
            return cases
