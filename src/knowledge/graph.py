"""
页面知识图谱 (Knowledge Graph)

以图结构存储探索结果: URL -> 元素 -> 操作 -> API映射 -> 子页面
支持JSON序列化/反序列化，可持久化保存。
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class ElementInfo:
    """页面元素信息"""
    tag: str
    type: str
    text: str = ""
    ref_id: str = ""
    id: str = ""
    name: str = ""
    href: str = ""
    aria_label: str = ""
    test_id: str = ""
    visible: bool = True
    disabled: bool = False
    locator_hints: Dict = field(default_factory=dict)


@dataclass
class FormInfo:
    """表单信息"""
    fields: List[ElementInfo] = field(default_factory=list)
    submit_button_ref: str = ""
    submit_button_text: str = ""
    action: str = ""  # form action URL


@dataclass
class ApiEndpoint:
    """API端点信息"""
    url: str
    method: str = "GET"
    trigger_element: str = ""  # 触发该API的元素描述
    status: int = 0
    duration_ms: int = 0


@dataclass
class PageKnowledge:
    """单个页面的完整知识"""
    url: str
    title: str = ""
    depth: int = 0
    explored_at: str = ""
    
    # 元素
    elements: List[ElementInfo] = field(default_factory=list)
    link_count: int = 0
    form_count: int = 0
    button_count: int = 0
    input_count: int = 0
    
    # API
    api_endpoints: List[ApiEndpoint] = field(default_factory=list)
    
    # 关系
    forms: List[FormInfo] = field(default_factory=list)
    child_links: List[str] = field(default_factory=list)  # 发现的子页面URL
    
    # 截图
    screenshot_path: str = ""
    
    # 快照
    snapshot_text: str = ""


class KnowledgeGraph:
    """页面知识图谱
    
    以URL为key的图结构:
    {
        "https://example.com/": PageKnowledge(...),
        "https://example.com/login": PageKnowledge(...),
        ...
    }
    """
    
    def __init__(self, start_url: str = ""):
        self.start_url = start_url
        self.created_at = datetime.now().isoformat()
        self.pages: Dict[str, PageKnowledge] = {}
        self.edges: Dict[str, List[str]] = {}  # URL -> [子URL列表]
        self.stats = {
            "total_pages": 0,
            "total_elements": 0,
            "total_forms": 0,
            "total_api_endpoints": 0,
            "max_depth_reached": 0,
        }
    
    def add_page(self, page: PageKnowledge):
        """添加页面知识"""
        url = self._normalize_url(page.url)
        self.pages[url] = page
        
        # 更新统计
        self.stats["total_pages"] = len(self.pages)
        self.stats["total_elements"] += len(page.elements)
        self.stats["total_forms"] += len(page.forms)
        self.stats["total_api_endpoints"] += len(page.api_endpoints)
        self.stats["max_depth_reached"] = max(self.stats["max_depth_reached"], page.depth)
        
        # 记录边关系
        if page.child_links:
            self.edges[url] = page.child_links
    
    def get_page(self, url: str) -> Optional[PageKnowledge]:
        """获取页面知识"""
        return self.pages.get(self._normalize_url(url))
    
    def has_page(self, url: str) -> bool:
        """检查页面是否已探索"""
        return self._normalize_url(url) in self.pages
    
    def get_all_urls(self) -> List[str]:
        """获取所有已探索的URL"""
        return list(self.pages.keys())
    
    def get_unexplored_links(self) -> List[str]:
        """获取尚未探索的链接"""
        all_links = set()
        for url, links in self.edges.items():
            for link in links:
                normalized = self._normalize_url(link)
                if normalized not in self.pages:
                    all_links.add(link)
        return list(all_links)
    
    def get_pages_at_depth(self, depth: int) -> List[PageKnowledge]:
        """获取特定深度的页面"""
        return [p for p in self.pages.values() if p.depth == depth]
    
    def get_summary(self) -> Dict:
        """获取图谱摘要"""
        return {
            "start_url": self.start_url,
            "created_at": self.created_at,
            **self.stats,
            "pages": {
                url: {
                    "title": p.title,
                    "depth": p.depth,
                    "elements": len(p.elements),
                    "forms": len(p.forms),
                    "links": len(p.child_links),
                    "api_endpoints": len(p.api_endpoints),
                }
                for url, p in self.pages.items()
            }
        }
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "start_url": self.start_url,
            "created_at": self.created_at,
            "pages": {
                url: asdict(page) for url, page in self.pages.items()
            },
            "edges": self.edges,
            "stats": self.stats,
        }
    
    def save(self, path: str):
        """保存到JSON文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'KnowledgeGraph':
        """从JSON文件加载"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        kg = cls(data.get("start_url", ""))
        kg.created_at = data.get("created_at", "")
        kg.stats = data.get("stats", kg.stats)
        kg.edges = data.get("edges", {})
        
        for url, page_data in data.get("pages", {}).items():
            page = PageKnowledge(
                url=page_data.get("url", url),
                title=page_data.get("title", ""),
                depth=page_data.get("depth", 0),
                explored_at=page_data.get("explored_at", ""),
                link_count=page_data.get("link_count", 0),
                form_count=page_data.get("form_count", 0),
                button_count=page_data.get("button_count", 0),
                input_count=page_data.get("input_count", 0),
                screenshot_path=page_data.get("screenshot_path", ""),
                snapshot_text=page_data.get("snapshot_text", ""),
            )
            # 恢复元素
            for el_data in page_data.get("elements", []):
                page.elements.append(ElementInfo(**el_data))
            # 恢复API
            for api_data in page_data.get("api_endpoints", []):
                page.api_endpoints.append(ApiEndpoint(**api_data))
            # 恢复表单
            for form_data in page_data.get("forms", []):
                fields = [ElementInfo(**f) for f in form_data.pop("fields", [])]
                form_data["fields"] = fields
                page.forms.append(FormInfo(**form_data))
            # 恢复子链接
            page.child_links = page_data.get("child_links", [])
            
            kg.pages[url] = page
        
        return kg
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """标准化URL (去除尾部斜杠和fragment)"""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # 去fragment
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/') or '/',
            parsed.params,
            parsed.query,
            ''  # no fragment
        ))
        return normalized
