# ❓ 常见问题 FAQ

## 入门

### Q: 我完全不懂 Python，能用吗？

能。你只需要：
1. 电脑上装 Python（[python.org](https://python.org) 下载，勾选 "Add to PATH"）
2. 编辑 `portfolio_data.json` 填入你的持仓（用记事本打开）
3. 双击运行（或终端输入 `python 05-scripts/rebuild.py`）
4. 双击 `portfolio_analysis.html` 查看

不需要写任何代码。如果有问题，运行 `python setup.py` 交互式引导配置。

### Q: 我不是程序员，这个对我有什么用？

Anchor 不是技术产品，是**投资纪律工具**。它帮你：
- 记录所有持仓，一目了然
- 自动检查规则（止损/止盈/时间到期）
- 生成可视看板，不用打开 N 个 App
- AI 辅助复盘，省去手动计算

### Q: 需要付费吗？

完全免费。代码开源（MIT），数据用免费 API，看板纯 HTML 零依赖。

## 数据

### Q: 我的持仓数据会上传到网上吗？

**不会。** `.gitignore` 已排除所有敏感文件。如果你不用 Git，数据只在本地。如果上传 GitHub，敏感文件会被自动忽略。

### Q: portfolio_data.json 怎么写？

参考 `06-dashboard/portfolio_data_example.json`。核心字段：
- `holdings_summary`: 基金列表（name/mv/pnl/group）
- `stock_holdings`: 股票列表（name/shares/cost/price）
- `yuebao`: 余额宝金额
- `market`: 市场行情数据

详细说明运行 `python setup.py` 交互式配置。

### Q: 数据从哪里来？

优先级：`mx-data API（东方财富）→ AKShare → WebSearch → App 截图`

日常更新对 Claude 说"更新今日数据"即可自动获取。

### Q: 多久更新一次？

| 频率 | 操作 |
|:--|:--|
| 每日 | 收盘后更新 JSON → rebuild |
| 每周 | 仓位点检 + 生成周报 |
| 每月 | 月度归因 + 规则审议 |

## 看板

### Q: 看板打开是空白的？

检查：
1. `rebuild.py` 是否运行成功（终端没有报错）
2. 打开的是 `Desktop/portfolio_analysis.html`（不是 `06-dashboard/` 里的副本）
3. `portfolio_data.json` 是否有数据

### Q: 怎么让看板在手机上也能看？

部署 GitHub Pages 后自动适配移动端。或者直接发 HTML 文件到手机浏览器。

### Q: 能不能自定义颜色/布局？

可以。`rebuild.py` 的 HTML 模板是纯 CSS 变量，改 `:root` 块即可换主题。

## 规则

### Q: 为什么有这么多规则？太死板了吧？

规则是为了**管住情绪**。回测验证：109 笔实盘中，所有最大亏损都发生在违反规则时。规则不保证赚钱，但保证不死。

### Q: 我可以改规则吗？

当然。规则是你的，框架只是帮你执行。修改 `01-rules/` 下的文件，然后在 rebuild.py 中对应调整检查逻辑。

### Q: 浮亏为什么不加仓？

数据证明：个人投资者最大的亏损来自"越跌越买"。浮亏说明判断错了，加仓是加重错误。宁可错过反弹，也不加仓亏损品种。

## 技术

### Q: 需要安装什么依赖？

- Python 3.8+
- 基础库：json, os, shutil（Python 自带）
- 可选：pandas（Excel 导出用）

```bash
pip install pandas  # 仅 Excel 导出需要
```

### Q: 怎么部署到服务器？

```bash
# Docker (coming soon)
docker run -v ./your_data:/data killian99cm/anchor-system

# 手动
crontab -e
# 添加：0 20 * * * cd /path/to/anchor && python 05-scripts/rebuild.py
```

### Q: 能接入其他数据源吗？

可以。修改 `rebuild.py` 的数据加载逻辑，适配任意 JSON 格式。或者对 Claude 说"帮我接入 XXX 数据源"。

### Q: 怎么贡献代码？

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎 PR！
