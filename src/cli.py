"""AgentForWebUITest CLI — 命令行工具

用法:
    webui-test test <url>                # 测试指定URL
    webui-test explore <url>             # 仅探索
    webui-test suite <url>               # TestSuite 编排执行
    webui-test suite <url> --preset smoke   # 冒烟测试
    webui-test suite <url> --filter "P0+form"  # 过滤
    webui-test check                     # 环境自检
    webui-test version                   # 版本信息
"""

import sys
import subprocess
from pathlib import Path

VERSION = "0.5.0"


def cmd_test(url: str) -> bool:
    """运行完整测试"""
    from src.agent import WebUITestAgent
    agent = WebUITestAgent()
    result = agent.run(f"测试 {url}")
    if result.get("test_case_count", 0) > 0:
        print(f"\n✅ 完成: 探索 {result.get('pages_explored', 0)} 页面, 生成 {result['test_case_count']} 用例")
        return True
    print("\n❌ 测试未生成用例")
    return False


def cmd_explore(url: str) -> bool:
    """仅探索页面"""
    from src.explorer import Explorer
    from src.strategy import StrategyEngine

    engine = StrategyEngine()
    strategy = engine.parse(f"快速探索 {url}")
    explorer = Explorer(strategy)
    pages = explorer.explore(url)
    print(f"\n✅ 探索完成: {len(pages)} 页面")
    return True


def cmd_suite(url: str, preset: str = "regression", filter_expr: str = None,
              split: bool = False) -> bool:
    """TestSuite 编排执行"""
    from src.agent import WebUITestAgent
    
    agent = WebUITestAgent()
    result = agent.run_with_suite(
        f"测试 {url}",
        preset=preset,
        filter_expr=filter_expr,
        split_by_category=split
    )
    
    summary = result.get("suite_summary", {})
    failed = summary.get("failed", 0) + summary.get("error", 0)
    
    if summary:
        print(f"\n{'✅ 全部通过!' if failed == 0 else f'❌ {failed} 失败'}")
    return failed == 0


def cmd_check() -> bool:
    """环境自检"""
    all_ok = True
    results = []

    def _check(name, ok, detail=""):
        nonlocal all_ok
        if not ok:
            all_ok = False
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if detail:
            print(f"     → {detail}")

    print("\n🔍 AgentForWebUITest 环境自检")
    print("=" * 50)

    vi = sys.version_info
    _check(f"Python {vi.major}.{vi.minor}.{vi.micro} ≥ 3.9", vi >= (3, 9))

    try:
        import yaml
        _check("pyyaml", True, f"v{yaml.__version__}")
    except ImportError:
        _check("pyyaml", False, "请运行: pip install pyyaml")

    try:
        r = subprocess.run(["agent-browser", "--version"], capture_output=True, text=True, timeout=10)
        _check("agent-browser", r.returncode == 0, r.stdout.strip() if r.returncode == 0 else r.stderr.strip())
    except FileNotFoundError:
        _check("agent-browser", False, "未安装: npm install -g agent-browser")
    except Exception as e:
        _check("agent-browser", False, str(e))

    try:
        r = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True, timeout=10)
        _check("Chrome", True, r.stdout.strip())
    except FileNotFoundError:
        try:
            r = subprocess.run(["chromium", "--version"], capture_output=True, text=True, timeout=10)
            _check("Chromium", True, r.stdout.strip())
        except FileNotFoundError:
            _check("Chrome/Chromium", False, "请安装 Chrome 或 Chromium")

    config_path = Path(__file__).parent.parent / "config.yaml"
    _check("config.yaml", config_path.exists())

    modules = ["agent", "explorer", "planner", "executor", "healer", "reporter", "judge", "analyzer", "suite"]
    for mod in modules:
        try:
            __import__(f"src.{mod}")
            _check(f"src.{mod}", True)
        except ImportError as e:
            _check(f"src.{mod}", False, str(e))

    print("=" * 50)
    if all_ok:
        print("  🎉 环境就绪，可以正常使用")
    else:
        print("  ⚠️  存在异常，请根据上述提示修复")
    return all_ok


COMMANDS = {
    "test":    (cmd_test,    "<url>                        测试指定URL"),
    "explore": (cmd_explore, "<url>                        仅探索页面"),
    "suite":   (cmd_suite,   "<url> [--preset] [--filter]  TestSuite编排执行"),
    "check":   (cmd_check,   "                             环境自检"),
    "version": (lambda: print(f"AgentForWebUITest v{VERSION}") or True, "                             版本信息"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(f"AgentForWebUITest CLI v{VERSION}")
        print()
        print("用法: webui-test <命令> [参数]")
        print()
        for name, (_, desc) in COMMANDS.items():
            print(f"  {name:<10s}  {desc}")
        print()
        print("suite 参数:")
        print("  --preset <name>    套件预设: smoke/critical/regression/full")
        print("  --filter <expr>    过滤表达式: P0+form, ~P3, url:/login/")
        print("  --split            按类别拆分套件")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"❌ 未知命令: {cmd}")
        print(f"   可用: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    func, _ = COMMANDS[cmd]
    args = sys.argv[2:]
    
    if cmd in ("test", "explore", "suite"):
        if not args:
            print(f"❌ {cmd} 需要 URL 参数")
            sys.exit(1)
        
        if cmd == "suite":
            # 解析 --preset / --filter / --split
            preset = "regression"
            filter_expr = None
            split = False
            
            i = 1
            url = args[0]
            while i < len(args):
                if args[i] == "--preset" and i + 1 < len(args):
                    preset = args[i + 1]
                    i += 2
                elif args[i] == "--filter" and i + 1 < len(args):
                    filter_expr = args[i + 1]
                    i += 2
                elif args[i] == "--split":
                    split = True
                    i += 1
                else:
                    i += 1
            
            success = func(url, preset=preset, filter_expr=filter_expr, split=split)
        else:
            success = func(args[0])
    else:
        success = func()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
