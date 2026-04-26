"""
AgentBrowser 驱动封装 (从 web-test-execution skill 提取)

为 AgentForWebUITest 提供统一的浏览器操作接口。
底层使用 agent-browser CLI (Chrome 147)。

核心原则:
  1. JS代码必须写入文件再eval（避免shell转义）
  2. eval返回值会被双引号包裹，需要json.loads解包
  3. 操作前清理旧会话防止CDP超时
"""

import json
import os
import re
import time
import shlex
from typing import Dict, List, Optional, Any, Tuple


class BrowserConfig:
    """浏览器配置"""
    def __init__(self, binary: str = "/root/.hermes/node/bin/agent-browser",
                 headless: bool = True, session_name: str = "webui-test",
                 default_timeout: int = 30):
        self.binary = binary
        self.headless = headless
        self.session_name = session_name
        self.default_timeout = default_timeout


class AgentBrowser:
    """agent-browser CLI 的 Python 封装
    
    提供与 Hermes 内置浏览器工具一致的调用接口。
    通过 Hermes 的 terminal() 函数执行 agent-browser 命令。
    """
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self._screenshots = []
        self._last_snapshot = None
        
        # 构建基础命令
        self._base_cmd = self.config.binary
        if not self.config.headless:
            self._base_cmd += " --headed"
        if self.config.session_name:
            self._base_cmd += f" --session {self.config.session_name}"
    
    def _run(self, cmd: str, timeout: int = None) -> str:
        """执行agent-browser命令"""
        from hermes_tools import terminal
        timeout = timeout or self.config.default_timeout
        full_cmd = f"{self._base_cmd} {cmd}"
        r = terminal(full_cmd, timeout=timeout)
        return r.get("output", "")
    
    def _run_eval(self, js_code: str, timeout: int = 15) -> Any:
        """执行JS代码 (自动处理文件写入和返回值解包)"""
        from hermes_tools import write_file
        
        write_file("/tmp/ab_eval.js", js_code)
        output = self._run(f'eval "$(cat /tmp/ab_eval.js)"', timeout=timeout)
        
        if "✗" in output:
            return None
        
        # 解包双引号
        if output.startswith('"') and output.endswith('"'):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                pass
        
        # 尝试解析JSON
        if isinstance(output, str) and (output.startswith('{') or output.startswith('[')):
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass
        
        return output
    
    # ========== 生命周期 ==========
    
    def close(self):
        """关闭所有浏览器会话"""
        from hermes_tools import terminal
        terminal(f"{self.config.binary} close --all 2>&1", timeout=10)
    
    # ========== 导航 ==========
    
    def navigate(self, url: str) -> bool:
        """导航到URL"""
        output = self._run(f"open '{url}'")
        if "✗" in output:
            self.close()
            output = self._run(f"open '{url}'")
        return "✓" in output
    
    def back(self):
        """后退"""
        self._run("back")
    
    def reload(self):
        """刷新"""
        self._run("reload")
    
    # ========== 快照 ==========
    
    def snapshot(self, interactive_only: bool = True) -> Dict:
        """获取页面快照"""
        flag = "-i" if interactive_only else ""
        output = self._run(f"snapshot {flag}")
        self._last_snapshot = output
        
        # 提取ref映射
        refs = {}
        for m in re.finditer(r'\[ref=e(\d+)\]', output):
            ref_id = f"@e{m.group(1)}"
            if ref_id not in refs:
                # 找到这个ref附近的描述文本
                line_start = max(0, output.rfind('\n', 0, m.start()))
                line_end = output.find('\n', m.end())
                line = output[line_start:line_end if line_end > 0 else len(output)]
                desc = re.sub(r'\s+', ' ', line.strip())[:80]
                refs[ref_id] = desc
        
        return {"snapshot": output, "refs": refs}
    
    # ========== 元素交互 ==========
    
    def click(self, ref: str) -> bool:
        """点击元素"""
        output = self._run(f"click {ref}")
        return "✓" in output
    
    def fill(self, ref: str, text: str) -> bool:
        """填写输入框"""
        safe_text = shlex.quote(text)
        output = self._run(f"fill {ref} {safe_text}")
        return "✓" in output
    
    def press(self, key: str) -> bool:
        """按键"""
        output = self._run(f"press {key}")
        return "✓" in output
    
    def check(self, ref: str) -> bool:
        """勾选复选框"""
        output = self._run(f"check {ref}")
        return "✓" in output
    
    def scroll(self, direction: str) -> bool:
        """滚动页面"""
        output = self._run(f"scroll {direction}")
        return "✓" in output
    
    # ========== 等待 ==========
    
    def wait(self, ms: int) -> bool:
        """等待毫秒"""
        output = self._run(f"wait {ms}", timeout=ms/1000 + 10)
        return "✓" in output
    
    # ========== JS执行 ==========
    
    def eval_js(self, js_code: str) -> Any:
        """执行JavaScript并返回结果"""
        return self._run_eval(js_code)
    
    # ========== 截图 ==========
    
    def screenshot(self, path: str = None, annotate: bool = False) -> str:
        """截图"""
        if path is None:
            path = f"/tmp/ab_screenshot_{int(time.time())}.png"
        
        flag = "--annotate" if annotate else ""
        output = self._run(f"screenshot {flag} {path}")
        
        if "✓" in output:
            self._screenshots.append(path)
            return path
        return None
    
    # ========== 信息获取 ==========
    
    def get_text(self, ref: str) -> str:
        """获取元素文本"""
        return self._run(f"get text {ref}").strip()
    
    def get_url(self) -> str:
        """获取当前URL"""
        result = self.eval_js("window.location.href")
        return str(result) if result else ""
    
    def get_title(self) -> str:
        """获取页面标题"""
        result = self.eval_js("document.title")
        return str(result) if result else ""
    
    def get_body_text(self, max_len: int = 3000) -> str:
        """获取页面body文本"""
        js = f"document.body.innerText.substring(0, {max_len})"
        result = self.eval_js(js)
        return str(result) if result else ""
    
    def is_visible(self, ref: str) -> bool:
        """检查元素是否可见"""
        output = self._run(f"is visible {ref}")
        return "✓" in output or "true" in output.lower()
    
    # ========== API拦截 ==========
    
    def inject_api_interceptor(self):
        """注入fetch/XHR拦截器"""
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
    
    # ========== 元素提取 ==========
    
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


# 全局单例
_global_browser = None

def get_browser(headless: bool = True, session_name: str = "webui-test") -> AgentBrowser:
    """获取全局浏览器实例"""
    global _global_browser
    if _global_browser is None:
        config = BrowserConfig(headless=headless, session_name=session_name)
        _global_browser = AgentBrowser(config)
    return _global_browser

def reset_browser():
    """重置浏览器"""
    global _global_browser
    if _global_browser:
        _global_browser.close()
        _global_browser = None
