# 🛠 Anchor 部署 SOP（稳定可复用 · 2026-09-01 固化）

> **目的**：部署不再"每次修"——流程固化 + 防回归测试 + 踩坑记录
> **强制**：每次部署必须走完本 SOP

---

## 一、部署前置（必跑）

```bash
# 1. 防回归测试（新增/修改代码后必跑）
cd C:/Users/lenovo/Desktop/Anchor/05-scripts
python test_stability.py        # 契约/pre_trade/API 冒烟

# 2. 本地编译检查
python -m py_compile <改动的 .py>
```

## 二、部署流程（固定顺序）

```bash
# 3. 打包（排除敏感）
cd C:/Users/lenovo/Desktop/Anchor-Software
tar czf /tmp/anchor-deploy.tgz --exclude='node_modules' --exclude='.git' \
  --exclude='*.env' --exclude='*.db' --exclude='anchor-deploy*.tgz' \
  --exclude='deploy/backup' --exclude='__pycache__' app deploy

# 4. 上传 + 备份 + 解压
scp -i ~/.ssh/anchor_prod /tmp/anchor-deploy.tgz ubuntu@122.51.64.43:/tmp/
ssh ... "sudo cp -r /opt/anchor-git /opt/anchor-git.bak-$(date +%m%d-%H%M) && sudo tar xzf /tmp/anchor-deploy.tgz -C /opt/anchor-git"

# 5. ⚠️ 重建必须 --build（force-recreate 不重建镜像=代码不生效！09-01 踩坑）
ssh ... "cd /opt/anchor-git && sudo docker compose -f deploy/docker-compose.yml up -d --build backend"

# 6. ⚠️ 全量 up -d（补 nginx——只重建 backend 会漏 nginx！09-01 两次踩坑）
ssh ... "cd /opt/anchor-git && sudo docker compose -f deploy/docker-compose.yml up -d"
```

## 三、部署后验证（必跑）

```bash
# 7. 冒烟验证（healthz + 核心 API）
ssh ... "curl -s -o /dev/null -w '%{http_code}' http://localhost/healthz"   # 期望 200
# 登录 → portfolio/market/summary/notification-settings/upload 全 200
```

## 四、DB schema 变更（固定流程）

```bash
# 变更前：查表结构 → ALTER 前备份
ssh ... "docker compose exec -T postgres pg_dump -U anchor -d anchor > /tmp/db-bak.sql"
# ALTER 示例（09-01 notification_settings 加 push 列教训）
ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS push_enabled boolean DEFAULT true;
# 变更后：测试相关接口
```

## 五、踩坑记录（勿再犯）

| # | 坑 | 避免 |
|---|-----|------|
| 1 | `--force-recreate` 不重建镜像 → 代码不生效 | 必须 `--build` |
| 2 | 只 `up -d --build backend` → nginx 缺失（前端打不开）| 必须 `up -d`（全量）|
| 3 | DB 表缺列 → 500（push_enabled）| 部署前查表结构 + ALTER 清单 |
| 4 | pydantic env_prefix=ANCHOR_ → 新 env 必须 `ANCHOR_` 前缀 | 加 env 时查 compose environment |
| 5 | 生产 dist 需本地 build 后部署（部署源码≠构建产物）| 前端改动：本地 `vite build` → tar dist → 部署 |
| 6 | AI_PROVIDERS_JSON env 覆盖代码厂商表 | 改厂商用代码（providers.py）不用 env JSON |
| 7 | 上传接口路径 = /api/v1/portfolio/holdings/upload（非 holdings/upload）| 查 router 前缀 |

## 六、应用跟随体系（同步机制）

```
规则手册 v3.x（体系权威）
  → extract_rule_contract.py（提取数值：止盈/阈值/四层/E1-E4）
  → AI-Collab/rule_contract.json（契约 13 键）
  → realtime_relay 分发 + 应用读契约渲染（前端/后端）
体系更新一处 → 契约自动更新 → 应用自动跟上（09-01 已含止盈 v3.6）
```

---

*SOP：2026-09-01 20:50 ｜ WorkBuddy。部署前必读必跑。*
