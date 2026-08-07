# Anchor Mobile Setup Guide

> 10 minutes | ¥0/month | After setup, you'll get a daily market briefing on WeChat automatically

---

## Step 1: Register for GitHub (if you haven't already)

1. Open https://github.com
2. Click Sign up → register with your email
3. Verify your email → log in

## Step 2: Create a Repository

1. Click `+` in the top-right → `New repository`
2. Repository name: `anchor-system`
3. Choose `Public`
4. Click `Create repository`

## Step 3: Upload Files

1. Drag the entire `Anchor` folder onto the GitHub web page
2. Wait for the upload to finish → click `Commit changes`

## Step 4: Register for Server酱 (WeChat push)

1. Open https://sct.ftqq.com
2. Click "Sign in" → scan the QR code with WeChat to log in
3. Click "SendKey" → copy your Key that starts with `SCT`

## Step 5: Set Up Secrets

On the GitHub repository page:

1. Click `Settings` → `Secrets and variables` → `Actions`
2. Click `New repository secret`
3. Add two secrets:

| Name | Value |
|------|------|
| `MX_APIKEY` | Your mx-data API Key |
| `SERVER_KEY` | Your Server酱 SCT Key |

## Step 6: Launch

1. Click the `Actions` tab at the top of the repository
2. Click `Anchor Daily Report`
3. Click `Run workflow` → `Run workflow`

---

## ✅ Done!

From now on, every trading day at 15:30, your WeChat will automatically receive:

```
⚓ Anchor · 2026-07-25
上证 3823 (-1.38%) | 科创50 1798 (+0.43%)
━━━━━━━━━━━━━━━━━━
📊 今日操作建议：全部不动
⚠️ 请回复持仓截图，AI将补充完整分析
```

---

## 🆘 Having trouble?

- GitHub Actions error → send me a screenshot
- Not receiving WeChat push → check the Server酱 Key
- mx-data can't fetch data → check the API Key
