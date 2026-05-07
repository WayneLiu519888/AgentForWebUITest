"""
PlaywrightBrowser — 基于 Playwright 的多浏览器驱动

支持 Chromium / Firefox / WebKit，实现 BrowserInterface。
snapshot 格式兼容 agent-browser 的 [ref=eN] 模式。
"""

import json
import os
import re
import time
import logging
from typing import Dict, List, Any, Optional

from .interface import BrowserInterface

logger = logging.getLogger(__name__)

# 尝试导入 playwright
try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Browser = None
    BrowserContext = None
    Page = None


class PlaywrightBrowser(BrowserInterface):
    """Playwright 多浏览器驱动

    支持 browser_type: "chromium" / "firefox" / "webkit"

    用法:
        browser = PlaywrightBrowser(browser_type="chromium", headless=True)
        browser.navigate("https://example.com")
        snap = browser.snapshot()
        browser.click("@e1")
        browser.close()
    """

    # ── 浏览器类型映射 ──
    BROWSER_MAP = {
        "chrome": "chromium",
        "chromium": "chromium",
        "firefox": "firefox",
        "webkit": "webkit",
    }

    def __init__(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        default_timeout: int = 30000,
    ):
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "playwright 未安装。请运行: pip install playwright && playwright install"
            )

        self._browser_type = self.BROWSER_MAP.get(browser_type, browser_type)
        if self._browser_type not in ("chromium", "firefox", "webkit"):
            raise ValueError(
                f"不支持的浏览器类型: {browser_type}。"
                f"可选: chromium, firefox, webkit"
            )

        self._headless = headless
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._default_timeout = default_timeout

        # Playwright 实例（懒初始化）
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # 记录截图
        self._screenshots: List[str] = []

        # 元素注册表：ref_id → element_handle 映射
        self._element_registry: Dict[str, Any] = {}

        self._init()

    def _init(self):
        """初始化 Playwright 和浏览器"""
        self._playwright = sync_playwright().start()

        launch_options = {"headless": self._headless}

        if self._browser_type == "chromium":
            self._browser = self._playwright.chromium.launch(**launch_options)
        elif self._browser_type == "firefox":
            self._browser = self._playwright.firefox.launch(**launch_options)
        elif self._browser_type == "webkit":
            self._browser = self._playwright.webkit.launch(**launch_options)

        self._context = self._browser.new_context(
            viewport=self._viewport,
            locale="zh-CN",
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(self._default_timeout)

    # ═══════════════════════════════════════════════════════════════
    # BrowserInterface 实现
    # ═══════════════════════════════════════════════════════════════

    def navigate(self, url: str) -> bool:
        """导航到URL"""
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            # 清空旧的元素注册表
            self._element_registry.clear()
            return True
        except Exception as e:
            logger.error(f"导航失败: {url} — {e}")
            return False

    def snapshot(self, interactive_only: bool = True) -> Dict:
        """生成页面快照（兼容 agent-browser [ref=eN] 格式）

        快照格式示例:
            - link "首页" [ref=e1]
            - button "提交" [ref=e2]
            - textbox "用户名" [ref=e3]
        """
        refs = {}
        lines = []
        self._element_registry.clear()
        ref_counter = [0]  # 用列表实现闭包引用

        # ARIA 角色到友好名称的映射
        ROLE_LABEL_MAP = {
            "link": "link",
            "button": "button",
            "textbox": "textbox",
            "searchbox": "textbox",
            "combobox": "combobox",
            "listbox": "listbox",
            "checkbox": "checkbox",
            "radio": "radio",
            "switch": "switch",
            "slider": "slider",
            "spinbutton": "spinbutton",
            "option": "option",
            "tab": "tab",
            "menuitem": "menuitem",
            "heading": "heading",
            "img": "image",
            "navigation": "navigation",
            "main": "main",
            "form": "form",
        }

        def get_role_label(el: dict) -> str:
            """从 aria 角色获取标签"""
            role = (el.get("role") or "").lower()
            return ROLE_LABEL_MAP.get(role, role or "generic")

        def build_name(el: dict) -> str:
            """构建元素名称"""
            name = el.get("name") or el.get("content") or ""
            # 截断过长文本
            if len(name) > 80:
                name = name[:77] + "..."
            return name

        def process_node(node: dict, depth: int = 0):
            """递归处理可访问性树节点"""
            role = node.get("role", "")
            name = build_name(node)
            is_interactive = (
                role in ("link", "button", "textbox", "searchbox",
                         "combobox", "listbox", "checkbox", "radio",
                         "switch", "slider", "spinbutton", "option",
                         "tab", "menuitem", "menu")
            )

            if is_interactive or not interactive_only:
                ref_counter[0] += 1
                ref_id = f"@e{ref_counter[0]}"
                ref_key = f"[ref=e{ref_counter[0]}]"

                role_label = get_role_label(node)
                indent = "  " * depth

                if name:
                    line = f'{indent}- {role_label} "{name}" {ref_key}'
                else:
                    line = f"{indent}- {role_label} {ref_key}"

                lines.append(line)
                refs[ref_id] = line.strip()[:80]

                # 注册元素，后续 click/fill 通过 JS 定位
                self._element_registry[ref_id] = {
                    "role": role,
                    "name": name,
                    "ref_key": ref_key,
                }

            # 递归处理子节点
            children = node.get("children", [])
            for child in children:
                process_node(child, depth + 1)

        try:
            # 使用 Playwright 的可访问性快照
            # page.accessibility.snapshot() 返回可访问性树
            ax_tree = self._page.accessibility.snapshot()

            if ax_tree:
                process_node(ax_tree)

            snapshot_text = "\n".join(lines) if lines else "(空白页面)"

            return {
                "snapshot": snapshot_text,
                "refs": refs,
            }

        except Exception as e:
            logger.error(f"快照生成失败: {e}")
            # 降级：使用 innerText
            try:
                body = self._page.inner_text("body")
                return {
                    "snapshot": f"(降级快照)\n{body[:5000]}",
                    "refs": {},
                }
            except Exception:
                return {"snapshot": "(快照不可用)", "refs": {}}

    def click(self, ref: str) -> bool:
        """点击元素

        Args:
            ref: 元素引用如 "@e3"
        """
        if ref not in self._element_registry:
            logger.warning(f"元素未注册: {ref}")
            return False

        el_info = self._element_registry[ref]
        role = el_info["role"]
        name = el_info["name"]

        try:
            # 通过 ARIA 属性定位并点击
            locator = self._locate_by_aria(role, name)
            if locator:
                locator.click(timeout=self._default_timeout)
                return True

            # 降级：通过命名角色定位
            if name:
                locator = self._page.get_by_role(role, name=name)
                locator.click(timeout=self._default_timeout)
                return True

            logger.warning(f"无法定位元素: {ref} (role={role}, name={name})")
            return False

        except Exception as e:
            logger.error(f"点击失败 {ref}: {e}")
            return False

    def fill(self, ref: str, text: str) -> bool:
        """填写输入框

        Args:
            ref: 元素引用如 "@e3"
            text: 要填入的文本
        """
        if ref not in self._element_registry:
            logger.warning(f"元素未注册: {ref}")
            return False

        el_info = self._element_registry[ref]
        role = el_info["role"]
        name = el_info["name"]

        try:
            locator = self._locate_by_aria(role, name)
            if locator:
                locator.fill(text, timeout=self._default_timeout)
                return True

            if name:
                locator = self._page.get_by_role(role, name=name)
                locator.fill(text, timeout=self._default_timeout)
                return True

            logger.warning(f"无法定位元素: {ref}")
            return False

        except Exception as e:
            logger.error(f"填写失败 {ref}: {e}")
            return False

    def screenshot(self, path: str = None, annotate: bool = False) -> Optional[str]:
        """截取页面截图

        Args:
            path: 保存路径
            annotate: 是否标注（Playwright 不支持标注，忽略）

        Returns:
            Optional[str]: 截图路径
        """
        if path is None:
            path = f"/tmp/pw_screenshot_{int(time.time())}.png"

        try:
            self._page.screenshot(path=path, full_page=True)
            self._screenshots.append(path)
            return path
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def eval_js(self, js_code: str) -> Any:
        """执行JavaScript并返回结果"""
        try:
            result = self._page.evaluate(js_code)
            # 如果返回的是字符串且看起来像JSON，尝试解析
            if isinstance(result, str) and (
                result.startswith("{") or result.startswith("[")
            ):
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    pass
            return result
        except Exception as e:
            logger.error(f"eval_js 执行失败: {e}")
            return None

    def extract_elements(self) -> List[Dict]:
        """提取页面上所有交互元素"""
        js = """
        (function() {
            var elements = [];
            var selectors = [
                'a[href]', 'button', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="tab"]',
                '[onclick]', '[data-testid]', '.btn', '[class*="button"]'
            ];
            var seen = new Set();

            selectors.forEach(function(sel) {
                try {
                    document.querySelectorAll(sel).forEach(function(el) {
                        if (seen.has(el)) return;
                        seen.add(el);

                        var rect = el.getBoundingClientRect();
                        var style = window.getComputedStyle(el);

                        elements.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || el.getAttribute('role') || 'generic',
                            id: el.id || null,
                            name: el.name || null,
                            className: (el.className && typeof el.className === 'string') ? el.className : null,
                            text: (el.textContent || el.value || el.placeholder || '').trim().substring(0, 200),
                            ariaLabel: el.getAttribute('aria-label') || null,
                            testId: el.getAttribute('data-testid') || null,
                            href: el.href || null,
                            visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                            position: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
                            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true'
                        });
                    });
                } catch(e) {}
            });

            return JSON.stringify(elements);
        })()
        """
        result = self.eval_js(js)
        return result if isinstance(result, list) else []

    def close(self):
        """关闭浏览器，释放所有资源"""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning(f"浏览器关闭异常: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._element_registry.clear()

    def get_browser_info(self) -> Dict:
        """获取浏览器信息"""
        return {
            "name": self._browser_type,
            "headless": self._headless,
            "viewport": self._viewport,
            "timeout_ms": self._default_timeout,
        }

    # ═══════════════════════════════════════════════════════════════
    # 扩展方法（兼容 AgentBrowser 的完整接口）
    # ═══════════════════════════════════════════════════════════════

    def wait(self, ms: int) -> bool:
        """等待指定毫秒"""
        try:
            self._page.wait_for_timeout(ms)
            return True
        except Exception:
            return False

    def scroll(self, direction: str) -> bool:
        """滚动页面"""
        try:
            if direction == "down":
                self._page.evaluate("window.scrollBy(0, window.innerHeight)")
            elif direction == "up":
                self._page.evaluate("window.scrollBy(0, -window.innerHeight)")
            else:
                self._page.evaluate(f"window.scrollBy(0, {direction})")
            return True
        except Exception as e:
            logger.error(f"滚动失败: {e}")
            return False

    def back(self):
        """后退"""
        try:
            self._page.go_back()
        except Exception as e:
            logger.error(f"后退失败: {e}")

    def reload(self):
        """刷新页面"""
        try:
            self._page.reload()
        except Exception as e:
            logger.error(f"刷新失败: {e}")

    def press(self, key: str) -> bool:
        """按键"""
        try:
            self._page.keyboard.press(key)
            return True
        except Exception as e:
            logger.error(f"按键失败: {e}")
            return False

    def check(self, ref: str) -> bool:
        """勾选复选框"""
        if ref not in self._element_registry:
            return False
        el_info = self._element_registry[ref]
        try:
            locator = self._locate_by_aria(el_info["role"], el_info["name"])
            if locator:
                locator.check(timeout=self._default_timeout)
                return True
            return False
        except Exception as e:
            logger.error(f"勾选失败 {ref}: {e}")
            return False

    def get_text(self, ref: str) -> str:
        """获取元素文本"""
        if ref not in self._element_registry:
            return ""
        el_info = self._element_registry[ref]
        try:
            locator = self._locate_by_aria(el_info["role"], el_info["name"])
            if locator:
                return locator.inner_text() or ""
            return ""
        except Exception:
            return ""

    def get_url(self) -> str:
        """获取当前URL"""
        try:
            return self._page.url
        except Exception:
            return ""

    def get_title(self) -> str:
        """获取页面标题"""
        try:
            return self._page.title()
        except Exception:
            return ""

    def get_body_text(self, max_len: int = 3000) -> str:
        """获取页面body文本"""
        try:
            text = self._page.inner_text("body")
            return text[:max_len] if text else ""
        except Exception:
            return ""

    def is_visible(self, ref: str) -> bool:
        """检查元素是否可见"""
        if ref not in self._element_registry:
            return False
        el_info = self._element_registry[ref]
        try:
            locator = self._locate_by_aria(el_info["role"], el_info["name"])
            if locator:
                return locator.is_visible()
            return False
        except Exception:
            return False

    # ── API 拦截（Playwright 实现） ──

    def inject_api_interceptor(self):
        """注入 fetch/XHR 拦截器"""
        js = """
(function() {
    if (window.__hermes_api_log) return 'already_injected';
    window.__hermes_api_log = [];
    window.__hermes_active_trigger = null;

    var origFetch = window.fetch;
    window.fetch = function(url, opts) {
        var start = performance.now();
        var trigger = window.__hermes_active_trigger;
        opts = opts || {};
        var req = { url: typeof url === 'string' ? url : url.url, method: (opts.method || 'GET').toUpperCase() };

        return origFetch.apply(this, arguments).then(function(r) {
            var clone = r.clone();
            var dur = performance.now() - start;
            clone.text().then(function(body) {
                window.__hermes_api_log.push({
                    request: req, response: { status: r.status, body: (body||'').substring(0, 5000) },
                    timing: { duration: Math.round(dur), timestamp: new Date().toISOString() },
                    trigger: trigger
                });
            }).catch(function(){});
            return r;
        });
    };

    window.__hermes_set_trigger = function(d) { window.__hermes_active_trigger = d; };
    window.__hermes_clear_trigger = function() { window.__hermes_active_trigger = null; };
    window.__hermes_get_api_log = function() { return window.__hermes_api_log; };
    window.__hermes_clear_api_log = function() { window.__hermes_api_log = []; };
    return 'injected';
})()
"""
        return self.eval_js(js)

    def get_api_log(self) -> List:
        """获取API调用日志"""
        result = self.eval_js("JSON.stringify(window.__hermes_get_api_log())")
        return result if isinstance(result, list) else []

    def clear_api_log(self):
        """清除API日志"""
        self.eval_js("window.__hermes_clear_api_log()")

    def set_trigger(self, desc: dict):
        """设置API触发器"""
        self.eval_js(f"window.__hermes_set_trigger({json.dumps(desc)})")

    def clear_trigger(self):
        """清除API触发器"""
        self.eval_js("window.__hermes_clear_trigger()")

    # ═══════════════════════════════════════════════════════════════
    # 内部辅助方法
    # ═══════════════════════════════════════════════════════════════

    def _locate_by_aria(self, role: str, name: str):
        """通过 ARIA 角色和名称定位元素"""
        if not name:
            return self._page.get_by_role(role)
        # 精确匹配
        locator = self._page.get_by_role(role, name=name)
        if locator.count() > 0:
            return locator.first
        # 包含匹配
        locator = self._page.get_by_role(role, name=re.compile(re.escape(name)))
        if locator.count() > 0:
            return locator.first
        return None

    @property
    def page(self) -> Optional[Page]:
        """获取底层 Playwright Page 对象（高级用法）"""
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        """获取底层 BrowserContext"""
        return self._context
