"""
自愈选择器 (Self-Healing Selector) — 迭代3核心模块

当标准元素定位失败时，自动尝试多种降级策略:
  1. CSS选择器 → 2. XPath → 3. 文本内容 → 4. aria-label → 5. data-testid → 6. 模糊匹配

记录愈合历史，支持自学习：记住成功的选择器策略用于后续步骤。

用法:
    from src.healer import SelectorHealer
    healer = SelectorHealer()
    ref_id = healer.find_element(browser, "登录按钮", page_context)
"""

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class HealingRecord:
    """一次愈合记录"""
    timestamp: str = ""
    original_target: str = ""            # 原始目标描述
    failed_selectors: List[str] = field(default_factory=list)  # 失败的策略
    successful_strategy: str = ""        # 最终成功的策略名
    resolved_ref: str = ""               # 解析到的ref ID
    resolved_description: str = ""       # 匹配到的元素描述
    confidence: float = 0.0              # 匹配置信度 (0.0-1.0)
    page_url: str = ""                   # 发生时的页面URL
    attempts: int = 0                    # 尝试次数

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HealerConfig:
    """自愈器配置"""
    enable_learning: bool = True          # 启用自学习
    max_learning_entries: int = 100       # 最大学习条目数
    fuzzy_threshold: float = 0.6          # 模糊匹配阈值
    timeout_per_strategy_ms: int = 3000   # 每个策略超时
    strategy_order: List[str] = field(default_factory=lambda: [
        "css_selector",
        "xpath",
        "text_content",
        "aria_label",
        "data_testid",
        "fuzzy_text",
    ])


# ═══════════════════════════════════════════════════════════════
# SelectorHealer
# ═══════════════════════════════════════════════════════════════

class SelectorHealer:
    """自愈选择器

    多策略降级链: 当一个定位策略失败时自动尝试下一个。
    记录愈合历史，支持自学习——记住成功策略。

    用法:
        healer = SelectorHealer()
        ref = healer.find_element(browser, "用户名输入框", page_context)
        if ref:
            browser.fill(ref, "admin")
    """

    # 策略优先级权重（越高越优先）
    STRATEGY_WEIGHTS = {
        "css_selector": 10,
        "xpath": 9,
        "text_content": 8,
        "aria_label": 7,
        "data_testid": 8,
        "fuzzy_text": 5,
    }

    def __init__(self, config: HealerConfig = None):
        self.config = config or HealerConfig()
        self.healing_history: List[HealingRecord] = []
        self.last_strategy_used: str = ""
        self.last_confidence: float = 0.0

        # 自学习存储: target_pattern → [成功策略列表，按成功率排序]
        self._learning_cache: Dict[str, List[str]] = defaultdict(list)
        self._strategy_success_count: Dict[str, int] = defaultdict(int)

    def find_element(self, browser, target_desc: str,
                     page_context: Dict = None) -> Optional[str]:
        """核心方法: 使用多策略降级链定位元素

        Args:
            browser: AgentBrowser实例
            target_desc: 目标元素描述（文本、选择器、ref ID等）
            page_context: 页面上下文 {
                "snapshot": str,
                "refs": Dict[str, str],
                "source_page": str,
                "step_description": str,
            }

        Returns:
            str: 元素的ref ID（如 @e42），或 None
        """
        if not target_desc:
            logger.warning("find_element: 无目标描述")
            return None

        page_context = page_context or {}

        # 0. 如果已经是ref ID，直接返回
        if target_desc.startswith("@e"):
            self.last_strategy_used = "direct_ref"
            self.last_confidence = 1.0
            return target_desc

        # 检查自学习缓存: 是否有这个目标的成功策略
        strategy_order = self._get_strategy_order(target_desc)

        # 获取快照信息
        snapshot = page_context.get("snapshot", "")
        refs = page_context.get("refs", {})

        healing = HealingRecord(
            original_target=target_desc,
            page_url=page_context.get("source_page", ""),
            attempts=0,
        )

        # 尝试每个策略
        for strategy_name in strategy_order:
            healing.attempts += 1

            try:
                ref_id = self._try_strategy(
                    browser, target_desc, strategy_name, snapshot, refs, page_context)

                if ref_id:
                    healing.successful_strategy = strategy_name
                    healing.resolved_ref = ref_id
                    healing.confidence = self.last_confidence
                    healing.resolved_description = (
                        refs.get(ref_id, f"元素 {ref_id}") if refs else f"元素 {ref_id}"
                    )
                    healing.failed_selectors = [
                        s for s in strategy_order
                        if strategy_order.index(s) < strategy_order.index(strategy_name)
                    ]

                    # 记录愈合历史
                    self.healing_history.append(healing)
                    if len(self.healing_history) > self.config.max_learning_entries:
                        self.healing_history.pop(0)

                    # 自学习: 记录成功策略
                    self._learn_success(target_desc, strategy_name)

                    self.last_strategy_used = strategy_name
                    return ref_id
                else:
                    healing.failed_selectors.append(strategy_name)

            except Exception as e:
                logger.debug(f"策略 {strategy_name} 异常: {e}")
                healing.failed_selectors.append(strategy_name)

        # 所有策略都失败
        healing.successful_strategy = ""
        healing.resolved_ref = ""
        healing.confidence = 0.0
        self.healing_history.append(healing)

        self.last_strategy_used = "none"
        self.last_confidence = 0.0
        return None

    def _try_strategy(self, browser, target_desc: str, strategy_name: str,
                      snapshot: str, refs: Dict, page_context: Dict) -> Optional[str]:
        """尝试单个定位策略"""
        handler = getattr(self, f"_locate_by_{strategy_name}", None)

        if handler is None:
            logger.debug(f"未知策略: {strategy_name}")
            return None

        if callable(handler):
            return handler(browser, target_desc, snapshot, refs, page_context)

        return None

    # ── 策略1: CSS选择器 ──

    def _locate_by_css_selector(self, browser, target_desc: str,
                                 snapshot: str, refs: Dict,
                                 page_context: Dict) -> Optional[str]:
        """通过CSS选择器定位"""
        # 尝试直接解析为CSS选择器
        if self._looks_like_css(target_desc):
            # 在snapshot中搜索匹配
            ref_id = self._find_in_snapshot_by_pattern(
                snapshot, refs, target_desc, strategy="css")
            if ref_id:
                self.last_confidence = 0.9
                return ref_id

        # 尝试常用CSS模式: tag[attribute=value]
        patterns = [
            f"[id=\"{target_desc}\"]",
            f"[name=\"{target_desc}\"]",
            f"[class*=\"{target_desc}\"]",
            f".{target_desc}",
            f"#{target_desc}",
        ]
        for pat in patterns:
            ref_id = self._find_in_snapshot_by_pattern(
                snapshot, refs, pat, strategy="css")
            if ref_id:
                self.last_confidence = 0.75
                return ref_id

        return None

    @staticmethod
    def _looks_like_css(text: str) -> bool:
        """判断字符串是否像CSS选择器"""
        css_indicators = ['#', '.', '[', '>', '+', '~', ':']
        return any(c in text for c in css_indicators)

    # ── 策略2: XPath ──

    def _locate_by_xpath(self, browser, target_desc: str,
                          snapshot: str, refs: Dict,
                          page_context: Dict) -> Optional[str]:
        """通过XPath定位（基于快照文本匹配）"""
        # 从目标描述构建XPath-like模式
        # 例如: "登录按钮" → //button[contains(text(),'登录')]
        xpath_patterns = []

        # 如果目标包含标签名
        tag_match = re.match(r'^(button|input|a|select|textarea|div|span|form)\b',
                             target_desc, re.IGNORECASE)
        if tag_match:
            tag = tag_match.group(1).lower()
            rest = target_desc[tag_match.end():].strip()
            if rest:
                xpath_patterns.append(f"//{tag}[contains(text(),'{rest}')]")
                xpath_patterns.append(f"//{tag}[contains(@aria-label,'{rest}')]")
            xpath_patterns.append(f"//{tag}[contains(text(),'{target_desc}')]")
        else:
            # 通用匹配
            for tag in ['button', 'a', 'input', 'label', 'span', 'div']:
                xpath_patterns.append(f"//{tag}[contains(text(),'{target_desc}')]")
                xpath_patterns.append(f"//{tag}[contains(@aria-label,'{target_desc}')]")

        for pattern in xpath_patterns:
            ref_id = self._find_in_snapshot_by_pattern(
                snapshot, refs, pattern, strategy="xpath")
            if ref_id:
                self.last_confidence = 0.7
                return ref_id

        return None

    # ── 策略3: 文本内容 ──

    def _locate_by_text_content(self, browser, target_desc: str,
                                 snapshot: str, refs: Dict,
                                 page_context: Dict) -> Optional[str]:
        """通过文本内容定位"""
        if not snapshot:
            return None

        # 精确文本匹配
        ref_id = self._find_in_snapshot_by_exact_text(snapshot, refs, target_desc)
        if ref_id:
            self.last_confidence = 0.85
            return ref_id

        # 包含匹配
        ref_id = self._find_in_snapshot_by_contains_text(snapshot, refs, target_desc)
        if ref_id:
            self.last_confidence = 0.7
            return ref_id

        return None

    @staticmethod
    def _find_in_snapshot_by_exact_text(snapshot: str, refs: Dict,
                                         text: str) -> Optional[str]:
        """在快照中精确匹配文本对应的ref"""
        if not text:
            return None

        # 快照格式: 每行类似 "[ref=e42] text..."
        # 查找包含精确文本的行
        escaped = re.escape(text)
        for ref_id, desc in refs.items():
            # 检查ref描述是否包含目标文本
            if text.lower() in desc.lower():
                # 进一步检查是否是精确匹配
                pattern = re.compile(rf'\b{escaped}\b', re.IGNORECASE)
                if pattern.search(desc):
                    return ref_id

        # 在整个snapshot中搜索
        for line in snapshot.split('\n'):
            if text.lower() in line.lower():
                # 提取ref ID
                ref_match = re.search(r'\[ref=(e\d+)\]', line)
                if ref_match:
                    return f"@e{ref_match.group(1)}"

        return None

    @staticmethod
    def _find_in_snapshot_by_contains_text(snapshot: str, refs: Dict,
                                            text: str) -> Optional[str]:
        """在快照中包含文本匹配对应的ref"""
        if not text or not snapshot:
            return None

        for ref_id, desc in refs.items():
            if text.lower() in desc.lower():
                return ref_id

        for line in snapshot.split('\n'):
            if text.lower() in line.lower():
                ref_match = re.search(r'\[ref=(e\d+)\]', line)
                if ref_match:
                    return f"@e{ref_match.group(1)}"

        return None

    # ── 策略4: aria-label ──

    def _locate_by_aria_label(self, browser, target_desc: str,
                               snapshot: str, refs: Dict,
                               page_context: Dict) -> Optional[str]:
        """通过aria-label属性定位"""
        if not snapshot:
            return None

        # 搜索aria-label模式
        aria_pattern = re.compile(
            rf'aria-label=["\']([^"\']*{re.escape(target_desc)}[^"\']*)["\']',
            re.IGNORECASE
        )

        for line in snapshot.split('\n'):
            match = aria_pattern.search(line)
            if match:
                ref_match = re.search(r'\[ref=(e\d+)\]', line)
                if ref_match:
                    self.last_confidence = 0.75
                    return f"@e{ref_match.group(1)}"

        return None

    # ── 策略5: data-testid ──

    def _locate_by_data_testid(self, browser, target_desc: str,
                                snapshot: str, refs: Dict,
                                page_context: Dict) -> Optional[str]:
        """通过data-testid属性定位"""
        if not snapshot:
            return None

        # 搜索data-testid模式
        testid_pattern = re.compile(
            rf'data-testid=["\']([^"\']*{re.escape(target_desc)}[^"\']*)["\']',
            re.IGNORECASE
        )

        for line in snapshot.split('\n'):
            match = testid_pattern.search(line)
            if match:
                ref_match = re.search(r'\[ref=(e\d+)\]', line)
                if ref_match:
                    self.last_confidence = 0.8
                    return f"@e{ref_match.group(1)}"

        # 也尝试用target_desc直接作为testid
        for line in snapshot.split('\n'):
            if f'data-testid="{target_desc}"' in line.lower():
                ref_match = re.search(r'\[ref=(e\d+)\]', line)
                if ref_match:
                    self.last_confidence = 0.9
                    return f"@e{ref_match.group(1)}"

        return None

    # ── 策略6: 模糊匹配 ──

    def _locate_by_fuzzy_text(self, browser, target_desc: str,
                               snapshot: str, refs: Dict,
                               page_context: Dict) -> Optional[str]:
        """通过模糊文本匹配定位"""
        if not snapshot or not target_desc:
            return None

        best_ref = None
        best_score = 0.0
        threshold = self.config.fuzzy_threshold

        # 对每个ref描述计算相似度
        for ref_id, desc in refs.items():
            score = self._text_similarity(target_desc.lower(), desc.lower())
            if score > best_score and score >= threshold:
                best_score = score
                best_ref = ref_id

        if best_ref:
            self.last_confidence = best_score
            return best_ref

        # 如果refs为空，直接在snapshot行上做模糊匹配
        if not refs:
            words = target_desc.lower().split()
            for line in snapshot.split('\n'):
                line_lower = line.lower()
                score = sum(1 for w in words if w in line_lower) / max(len(words), 1)
                if score >= threshold:
                    ref_match = re.search(r'\[ref=(e\d+)\]', line)
                    if ref_match:
                        self.last_confidence = score
                        return f"@e{ref_match.group(1)}"

        return None

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """计算两个字符串的相似度 (0.0 - 1.0)"""
        if not a or not b:
            return 0.0

        # 完全匹配
        if a == b:
            return 1.0
        # 包含
        if a in b or b in a:
            return 0.85

        # 基于词重叠的Jaccard相似度
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b
        jaccard = len(intersection) / len(union) if union else 0.0

        # 基于字符的n-gram相似度（trigram）
        def ngrams(s, n=3):
            return set(s[i:i+n] for i in range(len(s) - n + 1))

        ng_a = ngrams(a)
        ng_b = ngrams(b)

        if ng_a and ng_b:
            ng_inter = ng_a & ng_b
            ng_union = ng_a | ng_b
            trigram_score = len(ng_inter) / len(ng_union) if ng_union else 0.0
        else:
            trigram_score = 0.0

        # 综合评分
        return 0.4 * jaccard + 0.6 * trigram_score

    # ── 快照搜索辅助 ──

    @staticmethod
    def _find_in_snapshot_by_pattern(snapshot: str, refs: Dict,
                                      pattern: str, strategy: str = "") -> Optional[str]:
        """在快照中按模式匹配"""
        if not snapshot or not pattern:
            return None

        # 如果是CSS选择器格式
        if strategy == "css":
            # 提取可能的ID、class、属性名
            id_match = re.search(r'#([\w-]+)', pattern)
            if id_match:
                search_id = id_match.group(1)
                # 在快照中搜索该ID
                for line in snapshot.split('\n'):
                    if f'id="{search_id}"' in line or f"id='{search_id}'" in line:
                        ref_match = re.search(r'\[ref=(e\d+)\]', line)
                        if ref_match:
                            return f"@e{ref_match.group(1)}"

            class_match = re.search(r'\.([\w-]+)', pattern)
            if class_match:
                search_class = class_match.group(1)
                for line in snapshot.split('\n'):
                    if search_class.lower() in line.lower():
                        if 'class="' in line or "class='" in line:
                            ref_match = re.search(r'\[ref=(e\d+)\]', line)
                            if ref_match:
                                return f"@e{ref_match.group(1)}"

            # 属性选择器 [attr=value]
            attr_match = re.search(r'\[(\w+)\s*=\s*["\']([^"\']+)["\']\]', pattern)
            if attr_match:
                attr_name, attr_val = attr_match.groups()
                search_str = f'{attr_name}="{attr_val}"'
                for line in snapshot.split('\n'):
                    if search_str.lower() in line.lower():
                        ref_match = re.search(r'\[ref=(e\d+)\]', line)
                        if ref_match:
                            return f"@e{ref_match.group(1)}"

        # XPath-like模式
        if strategy == "xpath":
            # 提取 contains(text(),'...') 中的文本
            text_match = re.search(r"contains\(text\(\),['\"]([^'\"]+)['\"]\)", pattern, re.IGNORECASE)
            aria_match = re.search(r"contains\(@aria-label,['\"]([^'\"]+)['\"]\)", pattern, re.IGNORECASE)

            search_text = text_match.group(1) if text_match else None
            aria_text = aria_match.group(1) if aria_match else None

            for ref_id, desc in refs.items():
                if search_text and search_text.lower() in desc.lower():
                    return ref_id
                if aria_text and aria_text.lower() in desc.lower():
                    return ref_id

        return None

    # ── 自学习 ──

    def _get_strategy_order(self, target_desc: str) -> List[str]:
        """获取策略顺序（考虑自学习优化）"""
        if not self.config.enable_learning:
            return self.config.strategy_order.copy()

        # 生成目标模式的key
        cache_key = self._normalize_target(target_desc)

        # 检查学习缓存
        if cache_key in self._learning_cache and self._learning_cache[cache_key]:
            learned = self._learning_cache[cache_key]
            # 将学习到的优先策略放在前面
            standard = self.config.strategy_order.copy()
            reordered = []
            for s in learned:
                if s in standard:
                    reordered.append(s)
                    standard.remove(s)
            return reordered + standard

        return self.config.strategy_order.copy()

    def _learn_success(self, target_desc: str, strategy_name: str):
        """记录成功策略"""
        if not self.config.enable_learning:
            return

        cache_key = self._normalize_target(target_desc)
        strategies = self._learning_cache[cache_key]

        # 移到最前（最近成功）
        if strategy_name in strategies:
            strategies.remove(strategy_name)
        strategies.insert(0, strategy_name)

        # 限制条目数
        if len(strategies) > 5:
            strategies.pop()

        self._learning_cache[cache_key] = strategies
        self._strategy_success_count[strategy_name] += 1

    @staticmethod
    def _normalize_target(target: str) -> str:
        """标准化目标描述用于缓存key"""
        # 去除多余空白，转小写
        normalized = re.sub(r'\s+', ' ', target.strip().lower())
        # 截断长度
        return normalized[:80]

    # ── 统计与查询 ──

    def get_healing_stats(self) -> Dict:
        """获取愈合统计"""
        total = len(self.healing_history)
        if total == 0:
            return {"total_healings": 0, "success_rate": 0.0, "strategies": {}}

        successful = sum(1 for h in self.healing_history if h.successful_strategy)
        strategy_counts = defaultdict(int)
        for h in self.healing_history:
            if h.successful_strategy:
                strategy_counts[h.successful_strategy] += 1

        return {
            "total_healings": total,
            "successful_healings": successful,
            "success_rate": round(successful / total * 100, 1),
            "strategies": dict(strategy_counts),
            "learning_entries": len(self._learning_cache),
        }

    def get_learned_strategies(self) -> Dict[str, List[str]]:
        """获取学习到的策略映射"""
        return dict(self._learning_cache)

    def reset_learning(self):
        """重置学习缓存"""
        self._learning_cache.clear()
        self._strategy_success_count.clear()
        self.healing_history.clear()
