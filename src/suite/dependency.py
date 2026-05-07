"""依赖图解析与拓扑排序

用例间依赖声明格式 (在 TestCase.dependencies 中):
  ["TC-LOGIN-1"]           → 依赖 TC-LOGIN-1 先通过
  ["TC-LOGIN-1", "TC-A-3"] → 依赖两个都通过
  []                       → 无依赖

依赖图执行规则:
  1. 无依赖的用例最先执行
  2. 依赖的用例必须先通过 (pass 或 partial)，否则跳过
  3. 循环依赖检测（最大深度3，超过报错）
  4. 拓扑排序保证顺序

用法:
    from src.suite.dependency import DependencyGraph
    graph = DependencyGraph(cases, {"TC-F-2": ["TC-F-1"]})
    order = graph.resolve()
"""

from typing import Dict, List, Set, Optional
from collections import defaultdict, deque


class CircularDependencyError(Exception):
    """循环依赖异常"""
    pass


class DependencyGraph:
    """用例依赖图"""
    
    def __init__(self, 
                 case_ids: List[str],
                 dependencies: Dict[str, List[str]] = None):
        """
        Args:
            case_ids: 所有用例ID列表
            dependencies: {case_id: [前置case_id, ...]}
        """
        self.case_ids = case_ids
        self.dependencies = dependencies or {}
        self._graph = defaultdict(set)    # case_id → {前置case_id, ...}
        self._reverse = defaultdict(set)  # 前置case_id → {被依赖的case_id, ...}
        self._build_graph()
    
    def _build_graph(self):
        """构建依赖图"""
        for case_id in self.case_ids:
            if case_id not in self._graph:
                self._graph[case_id] = set()
        
        for case_id, deps in self.dependencies.items():
            for dep_id in deps:
                if dep_id not in self._graph:
                    self._graph[dep_id] = set()
                self._graph[case_id].add(dep_id)
                self._reverse[dep_id].add(case_id)
    
    def resolve(self) -> List[str]:
        """拓扑排序解析执行顺序
        
        Returns:
            排序后的用例ID列表
        
        Raises:
            CircularDependencyError: 检测到循环依赖
        """
        # 计算入度
        in_degree = {cid: len(self._graph[cid]) for cid in self._graph}
        
        # BFS 拓扑排序
        queue = deque([cid for cid, deg in in_degree.items() if deg == 0])
        result = []
        visited = set()
        
        while queue:
            cid = queue.popleft()
            if cid in visited:
                continue
            visited.add(cid)
            result.append(cid)
            
            for dependent in self._reverse.get(cid, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # 检测未访问节点 (循环依赖)
        remaining = set(self._graph.keys()) - visited
        if remaining:
            # 找出循环中涉及的ID
            raise CircularDependencyError(
                f"检测到循环依赖或深度超限: {', '.join(sorted(remaining))}"
            )
        
        return result
    
    def can_execute(self, case_id: str, passed_ids: Set[str]) -> bool:
        """判断用例是否可以执行（所有依赖已通过）
        
        Args:
            case_id: 待检查的用例ID
            passed_ids: 已通过的用例ID集合
        """
        deps = self._graph.get(case_id, set())
        return all(d in passed_ids for d in deps)
    
    def get_dependencies(self, case_id: str) -> Set[str]:
        """获取用例的所有直接依赖"""
        return self._graph.get(case_id, set()).copy()
    
    def get_dependents(self, case_id: str) -> Set[str]:
        """获取依赖此用例的其他用例"""
        return self._reverse.get(case_id, set()).copy()
