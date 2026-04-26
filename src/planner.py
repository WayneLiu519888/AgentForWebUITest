"""
智能用例生成器 (Smart Test Case Planner) — 迭代2核心模块

从 KnowledgeGraph 自动生成结构化测试用例，覆盖5大类别:
  form    — 表单测试 (正向/空值/边界/特殊字符)
  button  — 按钮测试 (点击/可见性/禁用态)
  link    — 链接测试 (导航可达性/URL正确性)
  api     — API测试 (状态码/响应时间/触发链)
  page    — 页面测试 (加载/元素完整性/标题)

用法:
    from src.planner import TestCasePlanner, PlannerConfig
    planner = TestCasePlanner()
    cases = planner.plan(knowledge_graph)
    planner.save(cases, "reports/test_cases.json")
"""

import json
import os
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class TestStep:
    """单个测试步骤"""
    action: str          # type | click | navigate | select | wait | verify | scroll
    target: str          # 元素描述 (用于匹配知识图谱中的元素)
    value: str = ""      # 输入值或选项
    description: str = ""  # 人类可读描述
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TestExpectation:
    """测试预期"""
    type: str            # api_status | page_content | url_contains | element_visible | element_count | element_not_exist
    target: str          # 目标 (URL/选择器/元素描述)
    expected_value: str = ""  # 预期值/状态码
    operator: str = "equals"  # equals | contains | matches | greater_than | less_than
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TestCase:
    """结构化测试用例"""
    id: str              # TC-F-001 格式
    name: str            # 人类可读名称
    priority: str        # P0/P1/P2/P3
    category: str        # form | button | link | api | page
    source_page: str     # 来源页面URL
    tags: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    expectations: List[TestExpectation] = field(default_factory=list)
    description: str = ""
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        return d
    
    def summary(self) -> str:
        return (f"{self.id} [{self.priority}] {self.name} "
                f"({len(self.steps)}步, {len(self.expectations)}预期)")


@dataclass
class PlannerConfig:
    """用例生成配置"""
    cases_per_page: int = 10          # 每页最大生成用例数
    min_form_fields: int = 1          # 最少字段数才生成表单用例
    priority_distribution: Dict[str, float] = field(default_factory=lambda: {
        "P0": 0.20,
        "P1": 0.30,
        "P2": 0.30,
        "P3": 0.20,
    })
    category_weights: Dict[str, float] = field(default_factory=lambda: {
        "form": 0.35,
        "button": 0.20,
        "link": 0.15,
        "api": 0.20,
        "page": 0.10,
    })
    # 表单测试值库
    test_values: Dict[str, List[str]] = field(default_factory=lambda: {
        "valid": ["admin", "test@example.com", "John Doe", "1234567890", "Hello World"],
        "empty": [""],
        "boundary_min": ["a", "1"],
        "boundary_max": ["a" * 256, "1" * 100],
        "special_chars": ["<script>alert(1)</script>", "' OR '1'='1", "!@#$%^&*()", "你好世界"],
        "numeric": ["0", "-1", "999999", "3.14", "NaN"],
        "email": ["admin@test.com", "invalid-email", "@no-domain", "spaces in@email.com"],
    })


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def _slugify(text: str) -> str:
    """将文本转为安全的标识符"""
    text = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '_', text)
    return text.strip('_')[:40] or "unknown"


def _is_login_form(form, elements) -> bool:
    """判断是否为登录表单"""
    keywords = ['login', '登录', 'username', '用户名', 'password', '密码', 'signin', '登入']
    form_texts = []
    for f in form.fields:
        form_texts.append(f.text.lower())
        form_texts.append(f.name or '')
        form_texts.append(f.id or '')
        form_texts.append(f.aria_label or '')
    combined = ' '.join(form_texts).lower()
    return any(kw in combined for kw in keywords)


def _is_search_form(form, elements) -> bool:
    """判断是否为搜索表单"""
    keywords = ['search', '搜索', 'query', '查询', 'find', '查找']
    form_texts = []
    for f in form.fields:
        form_texts.append(f.text.lower())
        form_texts.append(f.name or '')
        form_texts.append(f.aria_label or '')
    combined = ' '.join(form_texts).lower()
    return any(kw in combined for kw in keywords)


# ═══════════════════════════════════════════════════════════════
# TestCasePlanner
# ═══════════════════════════════════════════════════════════════

class TestCasePlanner:
    """智能用例生成器
    
    从 KnowledgeGraph 自动生成结构化测试用例。
    
    用法:
        planner = TestCasePlanner(config)
        cases = planner.plan(knowledge_graph)
        for c in cases:
            print(c.summary())
    """
    
    def __init__(self, config: PlannerConfig = None):
        self.config = config or PlannerConfig()
        self._case_counter = defaultdict(int)
        self._rng = random.Random(42)  # 固定种子保证确定性
    
    def plan(self, knowledge_graph) -> List[TestCase]:
        """主入口: 从知识图谱生成全部测试用例
        
        Args:
            knowledge_graph: KnowledgeGraph 实例
            
        Returns:
            List[TestCase]: 生成的测试用例列表
        """
        all_cases = []
        
        print(f"\n[Planner] 开始生成测试用例...")
        print(f"[Planner] 页面数: {knowledge_graph.stats['total_pages']}, "
              f"表单数: {knowledge_graph.stats['total_forms']}, "
              f"API数: {knowledge_graph.stats['total_api_endpoints']}")
        
        for url, page in knowledge_graph.pages.items():
            page_name = _slugify(page.title or url)
            page_cases = []
            
            # 1. 表单测试
            if page.forms:
                form_cases = self._generate_form_tests(page, page.forms, page_name)
                page_cases.extend(form_cases)
            
            # 2. 按钮测试
            buttons = [e for e in page.elements if e.tag == 'button']
            if buttons:
                button_cases = self._generate_button_tests(page, buttons, page_name)
                page_cases.extend(button_cases)
            
            # 3. 链接测试
            links = [e for e in page.elements if e.tag == 'a' and e.href]
            if links:
                link_cases = self._generate_link_tests(page, links, page_name)
                page_cases.extend(link_cases)
            
            # 4. API测试
            if page.api_endpoints:
                api_cases = self._generate_api_tests(page, page.api_endpoints, page_name)
                page_cases.extend(api_cases)
            
            # 5. 页面级测试
            page_level = self._generate_page_tests(page, page_name)
            page_cases.extend(page_level)
            
            # 限制每页用例数
            if len(page_cases) > self.config.cases_per_page:
                # 按类别权重截断
                page_cases = self._truncate_by_weight(page_cases)
            
            all_cases.extend(page_cases)
            print(f"  [{page_name}] 生成 {len(page_cases)} 个用例")
        
        # 分配优先级
        all_cases = self._assign_priorities(all_cases)
        
        print(f"\n[Planner] 总计生成 {len(all_cases)} 个测试用例")
        cats = defaultdict(int)
        prios = defaultdict(int)
        for c in all_cases:
            cats[c.category] += 1
            prios[c.priority] += 1
        print(f"[Planner] 类别分布: {dict(cats)}")
        print(f"[Planner] 优先级分布: {dict(prios)}")
        
        return all_cases
    
    # ── 表单测试生成 ──
    
    def _generate_form_tests(self, page, forms, page_name: str) -> List[TestCase]:
        """为每个表单生成正向/负向测试"""
        cases = []
        
        for i, form in enumerate(forms):
            if len(form.fields) < self.config.min_form_fields:
                continue
            
            form_name = _slugify(form.submit_button_text or f"form_{i}")
            base_id = f"TC-F-{self._next_id('form')}"
            is_login = _is_login_form(form, page.elements)
            is_search = _is_search_form(form, page.elements)
            
            source_url = page.url
            
            # 1) 正向测试 (正常提交)
            steps = []
            for j, field in enumerate(form.fields):
                val = self._pick_test_value(field, "valid")
                target = self._describe_element(field)
                steps.append(TestStep(
                    action="type", target=target, value=val,
                    description=f"在 {target} 输入 '{val}'"
                ))
            
            if form.submit_button_text:
                steps.append(TestStep(
                    action="click", target=form.submit_button_text,
                    description=f"点击 {form.submit_button_text}"
                ))
            
            expectations = self._infer_expectations(page, form, "positive")
            
            cases.append(TestCase(
                id=base_id, name=f"{'登录' if is_login else '搜索' if is_search else '表单'}-正常提交",
                priority="P0" if (is_login or is_search) else "P2",
                category="form", source_page=source_url,
                tags=["smoke", "happy-path", "login"] if is_login else
                     ["smoke", "happy-path"] if is_search else ["happy-path"],
                steps=steps, expectations=expectations,
                description=f"正向测试: 填写所有字段并提交"
            ))
            
            # 2) 空值测试 (每个字段至少一个)
            for j, field in enumerate(form.fields):
                target = self._describe_element(field)
                steps_neg = []
                for k, f2 in enumerate(form.fields):
                    val = "" if k == j else self._pick_test_value(f2, "valid")
                    steps_neg.append(TestStep(
                        action="type", target=self._describe_element(f2), value=val,
                        description=f"在 {self._describe_element(f2)} 输入 '{val}'"
                    ))
                if form.submit_button_text:
                    steps_neg.append(TestStep(
                        action="click", target=form.submit_button_text,
                        description=f"点击 {form.submit_button_text}"
                    ))
                
                cases.append(TestCase(
                    id=f"{base_id}-E{j+1}",
                    name=f"空值输入-{target}",
                    priority="P2", category="form", source_page=source_url,
                    tags=["negative", "empty-value", "validation"],
                    steps=steps_neg,
                    expectations=[
                        TestExpectation(type="page_content", target="",
                                       expected_value="required|必填|请填写|不能为空",
                                       operator="matches"),
                    ],
                    description=f"负向测试: {target} 留空提交"
                ))
            
            # 3) 特殊字符测试 (仅对文本输入)
            text_fields = [f for f in form.fields 
                          if f.type in ('text', 'search', 'email', 'textarea', '')]
            if text_fields:
                for val_set, tag in [("special_chars", "特殊字符"), ("boundary_max", "超长输入")]:
                    target_field = text_fields[0]
                    target = self._describe_element(target_field)
                    val = self.config.test_values[val_set][0]
                    
                    steps_special = []
                    for f2 in form.fields:
                        v = val if f2 == target_field else self._pick_test_value(f2, "valid")
                        steps_special.append(TestStep(
                            action="type", target=self._describe_element(f2), value=v,
                            description=f"在 {self._describe_element(f2)} 输入 '{v[:30]}'"
                        ))
                    if form.submit_button_text:
                        steps_special.append(TestStep(
                            action="click", target=form.submit_button_text,
                            description=f"点击 {form.submit_button_text}"
                        ))
                    
                    cases.append(TestCase(
                        id=f"{base_id}-S{len(cases)}",
                        name=f"{tag}-{target}",
                        priority="P2" if val_set == "special_chars" else "P3",
                        category="form", source_page=source_url,
                        tags=["boundary", "special-chars"] if val_set == "special_chars" else ["boundary", "max-length"],
                        steps=steps_special,
                        expectations=[
                            TestExpectation(type="page_content", target="",
                                           expected_value="", operator="contains"),
                        ],
                        description=f"边界测试: {target} 输入{tag}"
                    ))
        
        return cases
    
    # ── 按钮测试生成 ──
    
    def _generate_button_tests(self, page, buttons, page_name: str) -> List[TestCase]:
        """为每个按钮生成点击测试"""
        cases = []
        
        for i, btn in enumerate(buttons):
            if not btn.visible:
                continue
            
            btn_text = btn.text or f"button_{i}"
            base_id = f"TC-B-{self._next_id('button')}"
            target = self._describe_element(btn)
            
            # 1) 可见性检查
            cases.append(TestCase(
                id=base_id,
                name=f"按钮可见-{btn_text[:20]}",
                priority="P3", category="button", source_page=page.url,
                tags=["ui-check", "visibility"],
                steps=[TestStep(action="verify", target=target,
                               description=f"验证按钮 {target} 可见")],
                expectations=[
                    TestExpectation(type="element_visible", target=target,
                                   expected_value="true", operator="equals"),
                ],
                description=f"验证按钮 {btn_text} 在页面上可见"
            ))
            
            # 2) 禁用态检查
            if btn.disabled:
                cases.append(TestCase(
                    id=f"{base_id}-D",
                    name=f"按钮禁用态-{btn_text[:20]}",
                    priority="P2", category="button", source_page=page.url,
                    tags=["ui-check", "disabled-state"],
                    steps=[TestStep(action="verify", target=target,
                                   description=f"验证按钮 {target} 处于禁用状态")],
                    expectations=[
                        TestExpectation(type="element_visible", target=target,
                                       expected_value="disabled", operator="equals"),
                    ],
                    description=f"验证按钮 {btn_text} 处于禁用状态"
                ))
            
            # 3) 点击行为测试 (仅对非禁用按钮)
            if not btn.disabled and btn_text:
                cases.append(TestCase(
                    id=f"{base_id}-CLK",
                    name=f"点击交互-{btn_text[:20]}",
                    priority="P1", category="button", source_page=page.url,
                    tags=["interaction", "click-behavior"],
                    steps=[TestStep(action="click", target=target,
                                   description=f"点击按钮 {target}")],
                    expectations=[
                        TestExpectation(type="page_content", target="",
                                       expected_value="", operator="contains"),
                    ],
                    description=f"验证点击按钮 {btn_text} 后的页面响应"
                ))
        
        return cases
    
    # ── 链接测试生成 ──
    
    def _generate_link_tests(self, page, links, page_name: str) -> List[TestCase]:
        """为链接生成导航测试"""
        cases = []
        
        # 去重：相同URL链接只测一次
        seen_urls = set()
        unique_links = []
        for link in links:
            if link.href and link.href not in seen_urls:
                seen_urls.add(link.href)
                unique_links.append(link)
        
        # 限制链接测试数量 (每页最多5个)
        sample_links = unique_links[:5]
        
        for i, link in enumerate(sample_links):
            base_id = f"TC-L-{self._next_id('link')}"
            link_text = link.text or link.href[:40]
            
            cases.append(TestCase(
                id=base_id,
                name=f"链接可达性-{link_text[:20]}",
                priority="P1", category="link", source_page=page.url,
                tags=["navigation", "link-check"],
                steps=[TestStep(action="navigate", target=link.href,
                               description=f"导航到 {link.href}")],
                expectations=[
                    TestExpectation(type="url_contains", target=link.href,
                                   expected_value=link.href.split('/')[-1] or '/',
                                   operator="contains"),
                ],
                description=f"验证链接 {link_text} 可正常导航"
            ))
        
        return cases
    
    # ── API测试生成 ──
    
    def _generate_api_tests(self, page, api_endpoints, page_name: str) -> List[TestCase]:
        """为API端点生成状态码和响应测试"""
        cases = []
        
        for i, ep in enumerate(api_endpoints):
            base_id = f"TC-A-{self._next_id('api')}"
            ep_desc = ep.url.split('/')[-1] or ep.url[:30]
            
            # 1) 状态码检查
            cases.append(TestCase(
                id=base_id,
                name=f"API状态码-{ep.method} {ep_desc}",
                priority="P1", category="api", source_page=page.url,
                tags=["api-check", "status-code"],
                steps=[TestStep(action="verify", target=ep.url,
                               description=f"等待API {ep.method} {ep.url} 完成")],
                expectations=[
                    TestExpectation(type="api_status", target=ep.url,
                                   expected_value=str(ep.status), operator="equals"),
                ],
                description=f"验证 {ep.method} {ep.url} 返回 {ep.status}"
            ))
            
            # 2) 响应时间 (如果 > 1000ms，标记为警告)
            if ep.duration_ms > 1000:
                cases.append(TestCase(
                    id=f"{base_id}-T",
                    name=f"API响应时间-{ep.method} {ep_desc}",
                    priority="P2", category="api", source_page=page.url,
                    tags=["api-check", "performance"],
                    steps=[TestStep(action="verify", target=ep.url,
                                   description=f"测量API {ep.method} {ep.url} 响应时间")],
                    expectations=[
                        TestExpectation(type="api_status", target=ep.url,
                                       expected_value="1000", operator="less_than"),
                    ],
                    description=f"验证 {ep.method} {ep.url} 响应时间 < 1000ms"
                ))
        
        return cases
    
    # ── 页面级测试生成 ──
    
    def _generate_page_tests(self, page, page_name: str) -> List[TestCase]:
        """为整个页面生成结构级测试"""
        cases = []
        base_id = f"TC-P-{self._next_id('page')}"
        
        # 1) 页面加载测试
        cases.append(TestCase(
            id=base_id,
            name=f"页面加载-{page_name}",
            priority="P0", category="page", source_page=page.url,
            tags=["smoke", "page-load"],
            steps=[TestStep(action="navigate", target=page.url,
                           description=f"导航到 {page.url}")],
            expectations=[
                TestExpectation(type="page_content", target="",
                               expected_value=page.title or page.url, operator="contains"),
            ],
            description=f"验证页面 {page.url} 可正常加载"
        ))
        
        # 2) 页面标题测试
        if page.title:
            cases.append(TestCase(
                id=f"{base_id}-TITLE",
                name=f"页面标题-{page_name}",
                priority="P3", category="page", source_page=page.url,
                tags=["ui-check", "title"],
                steps=[TestStep(action="verify", target="document.title",
                               description="检查页面标题")],
                expectations=[
                    TestExpectation(type="page_content", target="title",
                                   expected_value=page.title, operator="contains"),
                ],
                description=f"验证页面标题包含 '{page.title}'"
            ))
        
        # 3) 元素完整性测试
        if page.elements:
            element_count = len(page.elements)
            cases.append(TestCase(
                id=f"{base_id}-ELEM",
                name=f"元素完整性-{page_name}",
                priority="P2", category="page", source_page=page.url,
                tags=["ui-check", "element-count"],
                steps=[TestStep(action="verify", target="page",
                               description="统计页面元素数量")],
                expectations=[
                    TestExpectation(type="element_count", target="page",
                                   expected_value=str(max(1, element_count // 2)),
                                   operator="greater_than"),
                ],
                description=f"验证页面包含至少 {max(1, element_count // 2)} 个元素"
            ))
        
        return cases
    
    # ── 优先级分配 ──
    
    def _assign_priorities(self, cases: List[TestCase]) -> List[TestCase]:
        """按配置比例分配优先级，保留已显式标记的P0"""
        # 分离已分配和待分配
        fixed = [c for c in cases if c.priority == "P0"]
        flexible = [c for c in cases if c.priority != "P0"]
        
        if not flexible:
            return cases
        
        # 按比例分配
        dist = self.config.priority_distribution
        total = len(flexible)
        counts = {
            "P1": max(1, round(total * dist["P1"] / (1 - dist["P0"]))),
            "P2": max(1, round(total * dist["P2"] / (1 - dist["P0"]))),
            "P3": max(1, round(total * dist["P3"] / (1 - dist["P0"]))),
        }
        
        # 按类别排序 (form > api > button > link > page)
        category_order = {"form": 0, "api": 1, "button": 2, "link": 3, "page": 4}
        flexible.sort(key=lambda c: (category_order.get(c.category, 5), c.id))
        
        idx = 0
        for prio in ["P1", "P2", "P3"]:
            n = min(counts[prio], len(flexible) - idx)
            for i in range(n):
                if idx < len(flexible):
                    flexible[idx].priority = prio
                    idx += 1
        
        # 剩余的标记为P3
        for i in range(idx, len(flexible)):
            flexible[i].priority = "P3"
        
        return fixed + flexible
    
    # ── 辅助方法 ──
    
    def _next_id(self, category: str) -> int:
        """生成递增ID"""
        self._case_counter[category] += 1
        return self._case_counter[category]
    
    def _describe_element(self, element) -> str:
        """生成元素的人类可读描述"""
        parts = []
        if element.text:
            parts.append(element.text[:30])
        if element.name:
            parts.append(f"name={element.name}")
        if element.id:
            parts.append(f"id={element.id}")
        if element.aria_label:
            parts.append(f"aria={element.aria_label}")
        if element.test_id:
            parts.append(f"testid={element.test_id}")
        return parts[0] if parts else f"{element.tag}[{getattr(element, 'href', '')[:30]}]"
    
    def _pick_test_value(self, field, category: str) -> str:
        """根据字段类型和类别选择合适的测试值"""
        values = self.config.test_values.get(category, ["test"])
        
        # 根据字段类型调整
        if field.type == "email" or "email" in (field.name or "").lower():
            if category == "valid":
                return "admin@test.com"
            return self.config.test_values.get("email", ["test@test.com"])[0]
        elif field.type == "number" or "numeric" in (field.name or "").lower():
            if category == "valid":
                return "42"
            return self.config.test_values.get("numeric", ["0"])[0]
        
        return self._rng.choice(values) if len(values) > 1 else values[0]
    
    def _infer_expectations(self, page, form, scenario: str) -> List[TestExpectation]:
        """根据表单类型推断预期结果"""
        exps = []
        is_login = _is_login_form(form, page.elements)
        
        if scenario == "positive":
            if is_login:
                exps.append(TestExpectation(
                    type="url_contains", target="",
                    expected_value="dashboard|home|index|welcome", operator="matches"))
            else:
                exps.append(TestExpectation(
                    type="page_content", target="",
                    expected_value="success|成功|ok|完成|谢谢", operator="matches"))
        
        return exps
    
    def _truncate_by_weight(self, cases: List[TestCase]) -> List[TestCase]:
        """按类别权重截断用例列表"""
        weights = self.config.category_weights
        max_n = self.config.cases_per_page
        
        # 按类别分组
        by_category = defaultdict(list)
        for c in cases:
            if c.priority == "P0":
                by_category[c.category].append(c)
            else:
                by_category[c.category].append(c)
        
        result = []
        # 优先保留P0
        p0_cases = [c for c in cases if c.priority == "P0"]
        result.extend(p0_cases)
        
        remaining = max_n - len(p0_cases)
        if remaining <= 0:
            return result[:max_n]
        
        # 按权重分配
        non_p0 = [c for c in cases if c.priority != "P0"]
        # 按类别排序
        category_order = {"form": 0, "api": 1, "button": 2, "link": 3, "page": 4}
        non_p0.sort(key=lambda c: category_order.get(c.category, 5))
        
        # 按权重取前N个
        total_weight = sum(weights.get(c.category, 0.1) for c in non_p0)
        result.extend(non_p0[:remaining])
        
        return result[:max_n]
    
    # ── 序列化 ──
    
    def save(self, cases: List[TestCase], path: str) -> str:
        """保存用例到JSON文件"""
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_cases": len(cases),
            "planner_config": {
                "cases_per_page": self.config.cases_per_page,
                "priority_distribution": self.config.priority_distribution,
            },
            "statistics": self._statistics(cases),
            "cases": [c.to_dict() for c in cases],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Planner] 用例已保存: {path}")
        return path
    
    @staticmethod
    def _statistics(cases: List[TestCase]) -> Dict:
        """生成统计信息"""
        cats = defaultdict(int)
        prios = defaultdict(int)
        steps = 0
        exps = 0
        for c in cases:
            cats[c.category] += 1
            prios[c.priority] += 1
            steps += len(c.steps)
            exps += len(c.expectations)
        return {
            "total": len(cases),
            "by_category": dict(cats),
            "by_priority": dict(prios),
            "total_steps": steps,
            "total_expectations": exps,
            "avg_steps_per_case": round(steps / max(len(cases), 1), 1),
        }
    
    @staticmethod
    def load(path: str) -> List[TestCase]:
        """从JSON文件加载用例"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cases = []
        for c_data in data.get("cases", []):
            steps = [TestStep(
                action=s["action"], target=s.get("target", ""),
                value=s.get("value", ""), description=s.get("description", "")
            ) for s in c_data.get("steps", [])]
            
            exps = [TestExpectation(
                type=e["type"], target=e.get("target", ""),
                expected_value=e.get("expected_value", ""),
                operator=e.get("operator", "equals")
            ) for e in c_data.get("expectations", [])]
            
            cases.append(TestCase(
                id=c_data["id"], name=c_data["name"],
                priority=c_data["priority"], category=c_data["category"],
                source_page=c_data["source_page"],
                tags=c_data.get("tags", []), steps=steps,
                expectations=exps, description=c_data.get("description", ""),
                generated_at=c_data.get("generated_at", ""),
            ))
        
        return cases
    
    @staticmethod
    def summary(cases: List[TestCase]) -> str:
        """生成可读摘要"""
        lines = [
            f"总用例数: {len(cases)}",
            f"总步骤数: {sum(len(c.steps) for c in cases)}",
            f"总预期数: {sum(len(c.expectations) for c in cases)}",
            "",
            "--- 优先级分布 ---",
        ]
        for prio in ["P0", "P1", "P2", "P3"]:
            n = sum(1 for c in cases if c.priority == prio)
            lines.append(f"  {prio}: {n}")
        lines.append("")
        lines.append("--- 类别分布 ---")
        for cat in ["form", "api", "button", "link", "page"]:
            n = sum(1 for c in cases if c.category == cat)
            lines.append(f"  {cat}: {n}")
        return "\n".join(lines)
