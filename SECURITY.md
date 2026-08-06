# 安全策略

## 报告漏洞

如果你发现安全漏洞，**请勿公开提交 Issue**。

请通过 GitHub 的 "Report a vulnerability" 功能私密报告：
https://github.com/killian99cm/anchor-system/security/advisories/new

## 数据安全

本项目的安全核心是**保护个人持仓数据**：

### 本地用户
1. `.gitignore` 已排除所有敏感数据文件
2. 运行 `git status` 确认没有意外暂存敏感文件
3. 不要在 Issue/PR/Discussion 中粘贴持仓数据

### Fork 用户
1. Fork 后立即确认 `.gitignore` 生效
2. 首次推送前检查是否有敏感数据
3. 使用 `portfolio_data_example.json` 替代真实数据

## 支持的版本

| 版本 | 支持状态 |
|------|:--:|
| v3.3 | ✅ 当前 |
| v3.2 | ❌ 不再维护 |
| v3.1 | ❌ 不再维护 |

## CI/CD 安全

- GitHub Actions 使用固定版本（非 `@latest`）
- 推送操作限定了文件路径，防止意外覆盖
