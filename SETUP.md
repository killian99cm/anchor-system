# Anchor 移动端搭建指南

> 10分钟 | ¥0月费 | 完成后每天微信自动收到行情简报

---

## 第一步：注册 GitHub（如果还没有）

1. 打开 https://github.com
2. 点击 Sign up → 用邮箱注册
3. 验证邮箱 → 登录

## 第二步：创建仓库

1. 点击右上角 `+` → `New repository`
2. Repository name: `anchor-system`
3. 选择 `Public`
4. 点击 `Create repository`

## 第三步：上传文件

1. 把整个 `Anchor` 文件夹拖到 GitHub 网页上
2. 等文件上传完 → 点击 `Commit changes`

## 第四步：注册 Server酱（微信推送）

1. 打开 https://sct.ftqq.com
2. 点击「登入」→ 用微信扫码登录
3. 点击「SendKey」→ 复制你的 `SCT` 开头的 Key

## 第五步：设置密钥

在 GitHub 仓库页面：

1. 点击 `Settings` → `Secrets and variables` → `Actions`
2. 点击 `New repository secret`
3. 添加两个密钥：

| Name | Value |
|------|------|
| `MX_APIKEY` | 你的 mx-data API Key |
| `SERVER_KEY` | 你的 Server酱 SCT Key |

## 第六步：启动

1. 点击仓库顶部的 `Actions` 标签
2. 点击 `Anchor Daily Report`
3. 点击 `Run workflow` → `Run workflow`

---

## ✅ 完成！

以后每个交易日 15:30，你的微信会自动收到：

```
⚓ Anchor · 2026-07-25
上证 3823 (-1.38%) | 科创50 1798 (+0.43%)
━━━━━━━━━━━━━━━━━━
📊 今日操作建议：全部不动
⚠️ 请回复持仓截图，AI将补充完整分析
```

---

## 🆘 遇到问题？

- GitHub Actions 报错 → 发截图给我
- 微信收不到推送 → 检查 Server酱 Key
- mx-data 拉不到数据 → 检查 API Key
