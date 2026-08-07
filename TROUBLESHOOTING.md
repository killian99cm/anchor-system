# 🔧 常见问题排查

## 安装

### `python: command not found`

**原因**：Python 未安装或未加入 PATH。

**解决**：
1. 去 [python.org](https://python.org) 下载 Python 3.8+
2. 安装时 **勾选 "Add Python to PATH"**
3. 重新打开终端，输入 `python --version` 验证

### `ModuleNotFoundError: No module named 'xxx'`

**解决**：
```bash
pip install pandas   # Excel 导出需要
pip install requests # 如果需要手动获取数据（rebuild.py 不依赖此库）
```

大部分依赖 Python 自带，不需要额外安装。

## rebuild.py

### `FileNotFoundError: portfolio_data.json`

**原因**：`portfolio_data.json` 不在当前目录。

**解决**：
```bash
# 方式1: 用 setup.py 生成
python setup.py

# 方式2: 复制示例
cp 06-dashboard/portfolio_data_example.json portfolio_data.json

# 方式3: 在 Anchor 根目录运行
cd C:\Users\lenovo\Desktop\Anchor
python 05-scripts/rebuild.py
```

### `KeyError: 'xxx'`

**原因**：`portfolio_data.json` 缺少必需字段。

**解决**：对照 `portfolio_data_example.json` 检查你的 JSON 结构。或运行 `python setup.py --reset` 重新生成。

### 中文乱码

**原因**：终端编码问题（常见于 Git Bash）。

**解决**：文件内容是正确的（UTF-8），只是终端显示乱码。打开生成的 HTML 看板不会有问题。或在 PowerShell/CMD 中运行。

### `UnicodeDecodeError`

**原因**：配置文件不是 UTF-8 编码。

**解决**：用 VS Code / Notepad++ 打开 `portfolio_data.json`，另存为 UTF-8。

## 看板

### 看板空白/数据为 0

**检查清单**：
1. `rebuild.py` 运行了吗？看终端输出确认成功
2. 打开的是 `Desktop/portfolio_analysis.html` 还是旧副本？
3. `portfolio_data.json` 的 `total_assets` > 0 吗？
4. 浏览器控制台（F12）有报错吗？

### 图表不显示

**原因**：`chart_data` 数组为空或格式不对。

**解决**：确保 JSON 中有 `chart_data` 字段，格式：
```json
"chart_data": [
  {"d": "08-01", "sh": 3900, "star": 1700, "pnl": 100},
  {"d": "08-02", "sh": 3920, "star": 1715, "pnl": -50}
]
```

### 手机上看布局错乱

**原因**：看板针对桌面设计。

**解决**：
- GitHub Pages 版本自动适配移动端
- 本地版本在手机横屏查看效果更好
- 或部署到 GitHub Pages 后用手机访问

## GitHub

### 推送被拒绝

**原因**：GitHub 网络不通（常见于中国大陆）。

**解决**：
```bash
# 切换到 SSH
git remote set-url origin git@github.com:killian99cm/anchor-system.git

# 或配置代理
git config --global http.proxy http://127.0.0.1:7890
```

### GitHub Pages 不更新

**检查**：
1. Actions 是否跑完变绿？（https://github.com/你的用户名/anchor-system/actions）
2. Settings → Pages 是否选了 "GitHub Actions"？
3. 等 1-2 分钟，CDN 有缓存

### Fork 后怎么同步上游更新？

```bash
# 添加原仓库为 upstream
git remote add upstream https://github.com/killian99cm/anchor-system.git

# 拉取合并
git fetch upstream
git merge upstream/main

# 解决冲突后推送
git push origin main
```

## 数据

### mx-data 查询失败

**原因**：API Key 未配置或过期。

**解决**：
1. 去 https://dl.dfcfs.com/m/itc4 获取 API Key
2. 设置环境变量：`export MX_APIKEY=your_key`
3. 或直接用 WebSearch / App 数据手动填入 JSON

### 基金净值不更新

**原因**：场外基金净值通常在 20:00-22:00 才公布。

**解决**：等晚间再运行 rebuild。或先用当日估算值，次日修正。

---

如果以上都没解决你的问题，请提 Issue：
https://github.com/killian99cm/anchor-system/issues/new?template=bug_report.md
