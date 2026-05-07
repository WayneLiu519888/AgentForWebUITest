"""
BrowserInterface — 浏览器抽象基类

所有浏览器实现必须继承此接口，确保统一的调用契约。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BrowserInterface(ABC):
    """浏览器操作统一接口

    所有浏览器实现（AgentBrowser / PlaywrightBrowser 等）必须实现此接口。
    """

    @abstractmethod
    def navigate(self, url: str) -> bool:
        """导航到指定URL

        Args:
            url: 目标URL

        Returns:
            bool: 导航是否成功
        """
        ...

    @abstractmethod
    def snapshot(self, interactive_only: bool = True) -> Dict:
        """获取页面可访问性快照

        Args:
            interactive_only: 是否仅返回可交互元素

        Returns:
            Dict: {"snapshot": str, "refs": dict}
                snapshot: 格式化快照文本，每行包含 [ref=eN] 标记
                refs: {"@e1": "描述文本", "@e2": "描述文本", ...}
        """
        ...

    @abstractmethod
    def click(self, ref: str) -> bool:
        """点击元素

        Args:
            ref: 元素引用，如 "@e3"

        Returns:
            bool: 点击是否成功
        """
        ...

    @abstractmethod
    def fill(self, ref: str, text: str) -> bool:
        """填写输入框

        Args:
            ref: 元素引用，如 "@e3"
            text: 要填入的文本

        Returns:
            bool: 填写是否成功
        """
        ...

    @abstractmethod
    def screenshot(self, path: str = None, annotate: bool = False) -> Optional[str]:
        """截取页面截图

        Args:
            path: 保存路径（None 则自动生成）
            annotate: 是否标注元素

        Returns:
            Optional[str]: 截图文件路径，失败返回None
        """
        ...

    @abstractmethod
    def eval_js(self, js_code: str) -> Any:
        """执行JavaScript代码并返回结果

        Args:
            js_code: JavaScript代码字符串

        Returns:
            Any: JS执行返回值（自动解析JSON等）
        """
        ...

    @abstractmethod
    def extract_elements(self) -> List[Dict]:
        """提取页面上所有交互元素

        Returns:
            List[Dict]: 元素列表，每个元素包含:
                tag, type, id, name, className, text, ariaLabel,
                testId, href, visible, position, disabled
        """
        ...

    @abstractmethod
    def close(self):
        """关闭浏览器会话，释放资源"""
        ...

    @abstractmethod
    def get_browser_info(self) -> Dict:
        """获取浏览器信息

        Returns:
            Dict: {"name": str, "version": str, "headless": bool, ...}
        """
        ...
