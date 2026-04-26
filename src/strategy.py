"""
策略引擎 (Strategy Engine)

理解测试目标，确定测试策略。
当前版本（迭代1）提供基础骨架，后续迭代增强LLM推理。

职责:
  1. 解析用户指令 ("测试 https://xxx.com")
  2. 确定测试范围和深度
  3. 配置探索/执行参数
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class TestStrategy:
    """测试策略"""
    target_url: str
    mode: str = "full"  # full | quick | login_only | smoke
    max_depth: int = 3
    max_pages: int = 50
    same_origin_only: bool = True
    
    # 可选的认证信息
    auth: Optional[Dict] = None  # {username, password, login_url}
    
    # 排除模式
    exclude_patterns: List[str] = field(default_factory=list)
    
    # 焦点功能
    focus_areas: List[str] = field(default_factory=list)  # ["login", "search", "checkout"]
    
    def to_dict(self) -> Dict:
        return {
            "target_url": self.target_url,
            "mode": self.mode,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "same_origin_only": self.same_origin_only,
            "has_auth": self.auth is not None,
            "exclude_patterns": self.exclude_patterns,
            "focus_areas": self.focus_areas,
        }


class StrategyEngine:
    """策略引擎: 从用户指令解析测试策略
    
    当前版本使用规则解析，后续版本使用LLM理解复杂指令。
    
    用法:
        engine = StrategyEngine()
        strategy = engine.parse("测试 https://example.com")
    """
    
    def parse(self, user_instruction: str) -> TestStrategy:
        """解析用户指令为测试策略
        
        支持的指令格式:
            "测试 https://example.com"
            "快速测试 https://example.com (max_depth=1)"
            "测试 https://example.com，只测登录功能"
            "深度测试 https://example.com (max_depth=5)"
        """
        import re
        
        # 提取URL
        url_match = re.search(r'https?://[^\s\u4e00-\u9fff]+', user_instruction)
        if not url_match:
            raise ValueError(f"未找到URL: {user_instruction}")
        
        target_url = url_match.group(0).rstrip(')）')
        
        # 确定模式
        mode = "full"
        max_depth = 3
        max_pages = 50
        
        if "快速" in user_instruction or "quick" in user_instruction.lower():
            mode = "quick"
            max_depth = 1
            max_pages = 10
        elif "深度" in user_instruction or "deep" in user_instruction.lower():
            mode = "deep"
            max_depth = 5
            max_pages = 100
        elif "登录" in user_instruction or "login" in user_instruction.lower():
            mode = "login_only"
            max_depth = 2
            max_pages = 5
        
        # 自定义深度
        depth_match = re.search(r'max_depth[=:]\s*(\d+)', user_instruction)
        if depth_match:
            max_depth = int(depth_match.group(1))
        
        # 焦点区域
        focus_areas = []
        for area in ["登录", "搜索", "注册", "支付", "购物车"]:
            if area in user_instruction:
                focus_areas.append(area)
        
        strategy = TestStrategy(
            target_url=target_url,
            mode=mode,
            max_depth=max_depth,
            max_pages=max_pages,
            focus_areas=focus_areas,
        )
        
        print(f"[Strategy] 解析完成: mode={mode}, depth={max_depth}, pages={max_pages}")
        return strategy
