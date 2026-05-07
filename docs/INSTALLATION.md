# AgentForWebUITest — 安装指南

---

## 方式一：pip 安装 (推荐)

```bash
# 基本安装 (仅 Chrome/agent-browser)
pip install agent-for-webui-test

# 多浏览器支持 (Firefox/WebKit)
pip install "agent-for-webui-test[playwright]"
playwright install chromium firefox webkit

# 开发安装 (含测试工具)
pip install "agent-for-webui-test[dev]"
```

## 方式二：源码安装

```bash
git clone https://github.com/WayneLiu519888/AgentForWebUITest.git
cd AgentForWebUITest
pip install -e ".[dev]"
```

---

## 验证安装

```bash
# 环境自检
webui-test check

# 期望输出: 全部 ✅
#   ✅ Python 3.12.3
#   ✅ pyyaml v6.0.1
#   ✅ agent-browser 0.26.0
#   ✅ Chrome 147.0
#   ✅ src.suite
#   🎉 环境就绪

# 查看版本
webui-test version
# → AgentForWebUITest v0.5.0
```

---

## 浏览器环境准备

### Chrome (agent-browser)

```bash
# 安装 agent-browser CLI
npm install -g agent-browser@0.26.0

# 验证
agent-browser --version
```

### Playwright 多浏览器 (v0.5.0+)

```bash
# 安装 Playwright
pip install playwright
playwright install chromium firefox webkit

# 验证可用浏览器
python -c "from src.browser import list_available_browsers; print(list_available_browsers())"
# → ['agent-browser', 'chrome', 'firefox', 'webkit']
```

---

## Docker (可选)

```dockerfile
FROM python:3.12-slim

RUN pip install agent-for-webui-test
RUN apt-get update && apt-get install -y chromium

RUN npm install -g agent-browser@0.26.0

WORKDIR /app
COPY config.yaml .
CMD ["webui-test", "suite", "https://example.com", "--ci"]
```

---

## 升级

```bash
pip install --upgrade agent-for-webui-test
```

## 卸载

```bash
pip uninstall agent-for-webui-test
rm -rf reports/              # 删除生成的报告
```

---

## 故障排除

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: No module named 'src'` | 确认 pip install -e 在项目根目录执行 |
| `agent-browser: command not found` | 安装: `npm install -g agent-browser` |
| `playwright._impl._api_types.Error` | 运行: `playwright install` |
| `externally-managed-environment` | 加 `--break-system-packages` 或使用虚拟环境 |
