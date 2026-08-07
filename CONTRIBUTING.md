# 贡献指南

感谢你对 Anchor 投资管理系统的关注！

## 提交内容注意事项

### ⚠️ 严禁包含真实持仓数据
- 不要提交 `portfolio_data.json`
- 不要提交 `portfolio_snapshot.json`
- 不要提交 `portfolio_analysis.html`（含嵌入数据）
- 不要提交 `portfolio_holdings.xlsx`
- 使用 `portfolio_data_example.json` 进行测试

### 可以贡献的内容
- 🐛 Bug 修复（代码、脚本、HTML）
- 📖 文档改进（规则手册、README、注释）
- 🎨 可视化优化（看板 HTML/CSS）
- 🔧 新功能（数据采集、分析工具、回测）
- 🌐 翻译

## 提交流程

```bash
# 1. Fork 仓库
# 2. Clone 你的 Fork
git clone https://github.com/YOUR_USERNAME/anchor-system.git
cd anchor-system

# 3. 创建功能分支
git checkout -b feature/my-improvement

# 4. 用示例数据测试
cp 06-dashboard/portfolio_data_example.json portfolio_data.json
python 05-scripts/rebuild.py

# 5. 提交（不要包含敏感文件）
# .gitignore 已配置，git add 时会自动排除

# 6. Push 并提 PR
```

## 代码风格

- **Python**: 保持简单，不引入新依赖除非必要
- **HTML/CSS**: 深色终端风，零外部依赖
- **Markdown**: 中文文档，清晰优先

## Issue 规范

- 🐛 Bug 报告：描述复现步骤 + 预期行为
- 💡 功能建议：描述使用场景 + 为什么需要

## 行为准则

本项目遵循 [Contributor Covenant](CODE_OF_CONDUCT.md)。请保持友善和建设性。
