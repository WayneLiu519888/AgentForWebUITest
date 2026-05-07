"""过滤表达式解析器

语法:
  P0+P1              → 优先级 P0 和 P1
  form+api            → 类别 form 和 api
  P0+form             → P0 且 form 类别 (交集)
  ~P3                 → 排除 P3
  ~P3+~api            → 排除 P3 且 排除 api
  url:/login/         → URL 包含 /login/ 的页面用例
  name:登录           → name 包含 "登录"
  id:TC-F             → id 以 TC-F 开头

组合:
  P0+P1+form,~P3      → (P0或P1) 且 form 且 非P3
  smoke                → 预置别名: P0 (最多10个)

用法:
    from src.suite.filter import Filter
    f = Filter.parse("P0+form")
    f.matches(test_case)  # True/False
"""

from dataclasses import dataclass, field
from typing import List, Set, Optional
import re

# 预置别名
PRESET_ALIASES = {
    "smoke": "P0",
    "critical": "P0+P1",
    "regression": "P0+P1+P2",
    "all": "",
    "api": "api",
    "ui": "form+button+link+page",
}


@dataclass
class Filter:
    """用例过滤器
    
    支持优先级、类别、URL模式、名称模式的组合过滤。
    """
    priorities: Set[str] = field(default_factory=set)     # {"P0", "P1"}
    categories: Set[str] = field(default_factory=set)      # {"form", "api"}
    exclude_priorities: Set[str] = field(default_factory=set)
    exclude_categories: Set[str] = field(default_factory=set)
    url_pattern: Optional[str] = None                       # regex pattern
    name_pattern: Optional[str] = None
    id_prefix: Optional[str] = None
    max_cases: int = 0                                      # 0=无限制

    @classmethod
    def parse(cls, expr: str, max_cases: int = 0) -> "Filter":
        """解析过滤表达式
        
        Args:
            expr: "P0+form" / "P0+P1,~api" / "url:/login/+P0" / "smoke"
            max_cases: 最大用例数限制
        
        Returns:
            Filter 实例
        """
        f = cls(max_cases=max_cases)
        if not expr or expr == "*":
            return f

        # 预置别名
        if expr in PRESET_ALIASES:
            if expr == "smoke":
                f.max_cases = 10
            return cls.parse(PRESET_ALIASES[expr], max_cases=f.max_cases)

        # 按逗号分割多个条件
        parts = [p.strip() for p in expr.split(",") if p.strip()]
        f = cls(max_cases=max_cases)
        for part in parts:
            # 排除条件: ~P3, ~api
            if part.startswith("~"):
                item = part[1:]
                if item in ("P0", "P1", "P2", "P3"):
                    f.exclude_priorities.add(item)
                elif item in ("form", "button", "link", "api", "page"):
                    f.exclude_categories.add(item)
                continue

            # URL 模式: url:/login/
            if part.startswith("url:"):
                f.url_pattern = part[4:]
                continue

            # 名称模式: name:登录
            if part.startswith("name:"):
                f.name_pattern = part[5:]
                continue

            # ID 前缀: id:TC-F
            if part.startswith("id:"):
                f.id_prefix = part[3:]
                continue

            # 交集条件: P0+form (用+分割)
            sub_parts = part.split("+")
            for sp in sub_parts:
                sp = sp.strip()
                if sp in ("P0", "P1", "P2", "P3"):
                    f.priorities.add(sp)
                elif sp in ("form", "button", "link", "api", "page"):
                    f.categories.add(sp)

        return f

    def matches(self, case) -> bool:
        """检查用例是否匹配过滤条件
        
        Args:
            case: TestCase 实例 (有 priority, category, source_page, name, id 属性)
        """
        # 优先级过滤
        if self.priorities and case.priority not in self.priorities:
            return False
        if case.priority in self.exclude_priorities:
            return False

        # 类别过滤
        if self.categories and case.category not in self.categories:
            return False
        if case.category in self.exclude_categories:
            return False

        # URL 模式
        if self.url_pattern:
            url = getattr(case, "source_page", "")
            if not re.search(self.url_pattern, url):
                return False

        # 名称模式
        if self.name_pattern:
            name = getattr(case, "name", "")
            if self.name_pattern not in name:
                return False

        # ID 前缀
        if self.id_prefix:
            cid = getattr(case, "id", "")
            if not cid.startswith(self.id_prefix):
                return False

        return True

    def apply(self, cases: list) -> list:
        """过滤用例列表，返回匹配的用例"""
        result = [c for c in cases if self.matches(c)]
        
        # 优先级排序: P0 → P1 → P2 → P3
        prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        result.sort(key=lambda c: prio_order.get(c.priority, 99))
        
        # 数量限制
        if self.max_cases and len(result) > self.max_cases:
            result = result[:self.max_cases]
        
        return result

    def __repr__(self):
        parts = []
        if self.priorities:
            parts.append(f"prio={{{','.join(sorted(self.priorities))}}}")
        if self.categories:
            parts.append(f"cat={{{','.join(sorted(self.categories))}}}")
        if self.exclude_priorities:
            parts.append(f"~prio={{{','.join(sorted(self.exclude_priorities))}}}")
        if self.exclude_categories:
            parts.append(f"~cat={{{','.join(sorted(self.exclude_categories))}}}")
        if self.url_pattern:
            parts.append(f"url=/{self.url_pattern}/")
        if self.name_pattern:
            parts.append(f"name={self.name_pattern}")
        return f"Filter({', '.join(parts)})"
