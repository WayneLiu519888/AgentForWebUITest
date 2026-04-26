"""
递归页面探索引擎 (Explorer)

实现BFS递归探索: 从起始URL开始，发现所有内部链接，递归探索子页面，
构建完整的页面知识图谱。

核心算法:
  1. 导航到URL，等待加载
  2. 注入API拦截器
  3. 获取快照 + 提取元素
  4. 发现链接 -> 过滤内部链接 -> 加入队列
  5. 发现表单 -> 分析字段
  6. 重复直到队列为空或达到限制
"""

import time
import re
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Set, Optional
from collections import deque
from datetime import datetime

# 支持两种导入方式: 包内相对导入 和 外部绝对导入
try:
    from .browser import AgentBrowser, get_browser
    from .knowledge import KnowledgeGraph, PageKnowledge, ElementInfo, FormInfo, ApiEndpoint
except ImportError:
    from browser import AgentBrowser, get_browser
    from knowledge.graph import KnowledgeGraph, PageKnowledge, ElementInfo, FormInfo, ApiEndpoint


class ExplorerConfig:
    """探索配置"""
    def __init__(self,
                 max_depth: int = 3,
                 max_pages: int = 50,
                 wait_after_load: int = 2000,
                 same_origin_only: bool = True,
                 skip_patterns: List[str] = None):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.wait_after_load = wait_after_load
        self.same_origin_only = same_origin_only
        self.skip_patterns = skip_patterns or [
            r'logout', r'signout', r'delete', r'remove',
            r'javascript:', r'mailto:', r'tel:',
            r'\.pdf$', r'\.zip$', r'\.png$', r'\.jpg$',
        ]


class Explorer:
    """BFS递归页面探索器
    
    用法:
        explorer = Explorer(browser, config)
        graph = explorer.explore("https://example.com")
        print(f"发现 {graph.stats['total_pages']} 个页面")
    """
    
    def __init__(self, browser: AgentBrowser = None, config: ExplorerConfig = None):
        self.browser = browser or get_browser()
        self.config = config or ExplorerConfig()
        self._start_origin = ""
    
    def explore(self, start_url: str) -> KnowledgeGraph:
        """主入口: 探索整个系统
        
        Args:
            start_url: 系统起始URL
        
        Returns:
            KnowledgeGraph: 完整的页面知识图谱
        """
        graph = KnowledgeGraph(start_url)
        self._start_origin = self._get_origin(start_url)
        
        # BFS队列
        visited: Set[str] = set()
        queue = deque([(start_url, 0)])  # (url, depth)
        
        page_count = 0
        start_time = time.time()
        
        print(f"[Explorer] 开始探索: {start_url}")
        print(f"[Explorer] 最大深度: {self.config.max_depth}, 最大页面: {self.config.max_pages}")
        print()
        
        while queue and page_count < self.config.max_pages:
            url, depth = queue.popleft()
            normalized = self._normalize_url(url)
            
            # 跳过已访问
            if normalized in visited:
                continue
            visited.add(normalized)
            
            # 跳过深度限制
            if depth > self.config.max_depth:
                continue
            
            print(f"[{depth}] 探索: {url}")
            
            try:
                page = self._explore_page(url, depth)
                
                if page:
                    graph.add_page(page)
                    page_count += 1
                    
                    # 发现子链接 -> 加入队列
                    for link in page.child_links:
                        link_normalized = self._normalize_url(link)
                        if link_normalized not in visited:
                            queue.append((link, depth + 1))
                    
                    print(f"     ✅ 发现 {len(page.elements)} 元素, {len(page.child_links)} 链接, {len(page.api_endpoints)} API")
                else:
                    print(f"     ⚠️  探索失败")
                    
            except Exception as e:
                print(f"     ❌ 错误: {e}")
        
        elapsed = time.time() - start_time
        print(f"\n[Explorer] 完成! 探索 {page_count} 页面, 耗时 {elapsed:.1f}s")
        print(f"[Explorer] 统计: {graph.stats}")
        
        return graph
    
    def _explore_page(self, url: str, depth: int) -> Optional[PageKnowledge]:
        """探索单个页面"""
        
        # 1. 导航
        if not self.browser.navigate(url):
            return None
        
        # 2. 等待加载
        self.browser.wait(self.config.wait_after_load)
        
        # 3. 注入API拦截器 (第一次时)
        if not hasattr(self, '_interceptor_injected'):
            self.browser.inject_api_interceptor()
            self._interceptor_injected = True
        
        # 4. 获取基本信息
        current_url = self.browser.get_url()
        title = self.browser.get_title()
        
        # 5. 获取快照
        snapshot = self.browser.snapshot(interactive_only=True)
        
        # 6. 提取元素
        elements_raw = self.browser.extract_elements()
        
        # 7. 构建PageKnowledge
        page = PageKnowledge(
            url=current_url or url,
            title=title,
            depth=depth,
            explored_at=datetime.now().isoformat(),
            snapshot_text=snapshot.get("snapshot", ""),
        )
        
        # 8. 分类元素
        links = []
        forms_found = []
        current_form = None
        current_form_fields = []
        
        for el_raw in elements_raw:
            tag = el_raw.get("tag", "")
            el_type = el_raw.get("type", "generic")
            
            element = ElementInfo(
                tag=tag,
                type=el_type,
                text=el_raw.get("text", ""),
                id=el_raw.get("id", ""),
                name=el_raw.get("name", ""),
                href=el_raw.get("href", ""),
                aria_label=el_raw.get("ariaLabel", ""),
                test_id=el_raw.get("testId", ""),
                visible=el_raw.get("visible", False),
                disabled=el_raw.get("disabled", False),
            )
            
            page.elements.append(element)
            
            # 统计
            if tag == "a" and el_raw.get("href"):
                links.append(el_raw["href"])
                page.link_count += 1
            elif tag == "button":
                page.button_count += 1
            elif tag in ("input", "select", "textarea"):
                page.input_count += 1
            
            # 表单检测 (简化)
            if tag in ("input", "select", "textarea") and el_type not in ("submit", "button"):
                current_form_fields.append(element)
            elif (tag == "button" or el_type in ("submit", "button")) and current_form_fields:
                current_form = FormInfo(
                    fields=current_form_fields,
                    submit_button_text=element.text,
                )
                forms_found.append(current_form)
                current_form_fields = []
        
        # 如果有表单字段但没有提交按钮
        if current_form_fields:
            forms_found.append(FormInfo(fields=current_form_fields))
        
        page.forms = forms_found
        page.form_count = len(forms_found)
        
        # 9. 获取API日志
        api_log = self.browser.get_api_log()
        for api_call in api_log:
            req = api_call.get("request", {})
            resp = api_call.get("response", {})
            trigger = api_call.get("trigger", {})
            
            page.api_endpoints.append(ApiEndpoint(
                url=req.get("url", ""),
                method=req.get("method", "GET"),
                trigger_element=str(trigger) if trigger else "",
                status=resp.get("status", 0),
                duration_ms=api_call.get("timing", {}).get("duration", 0),
            ))
        
        # 10. 过滤内部链接
        child_links = self._filter_links(links, url)
        page.child_links = child_links
        
        # 11. 截图 (每10个页面截图一次以节省空间)
        if depth == 0 or len(child_links) > 5:
            path = f"/tmp/explore_{self._slugify(current_url or url)}.png"
            page.screenshot_path = self.browser.screenshot(path) or ""
        
        return page
    
    def _filter_links(self, links: List[str], current_url: str) -> List[str]:
        """过滤和规范化链接"""
        result = []
        seen = set()
        
        for link in links:
            # 跳过特殊协议
            if any(re.search(p, link, re.IGNORECASE) for p in self.config.skip_patterns):
                continue
            
            # 解析为绝对URL
            absolute = urljoin(current_url, link)
            
            # 同源检查
            if self.config.same_origin_only and self._start_origin:
                if not absolute.startswith(self._start_origin):
                    continue
            
            # 去重
            normalized = self._normalize_url(absolute)
            if normalized not in seen:
                seen.add(normalized)
                result.append(absolute)
        
        return result
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """标准化URL"""
        parsed = urlparse(url)
        # 去fragment，保留query
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/') or '/'}"
    
    @staticmethod
    def _get_origin(url: str) -> str:
        """获取origin"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    @staticmethod
    def _slugify(text: str) -> str:
        """将URL转为安全的文件名"""
        return re.sub(r'[^a-zA-Z0-9]', '_', text)[:50]
