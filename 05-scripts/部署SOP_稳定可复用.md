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

## 四、DB schema 变更（Alembic 迁移流程 · 2026-09-02 起接管）

> **铁律**：schema 变更一律走 Alembic migration——**禁止手动 ALTER**
> （push_enabled / report_review 手工补列曾致线上 500 的两大教训）。
> 生产库已于 2026-09-02 stamp baseline `79ecd7bf22a0`（现有 schema = 版本原点），
> alembic_version 已落库；此后新变更在 baseline 之上顺序叠加。

### 4.1 本地开发：改 model → 生成 → 审 → 升级

```bash
# 0) 改 models/xxx.py 后（不直接改库！）
cd C:/Users/lenovo/Desktop/Anchor-Software/app/backend
# 1) 生成迁移（自动 diff 本地 dev 库 sqlite vs Base.metadata）
alembic revision --autogenerate -m "描述：如 push_enabled 推送到 notification_settings"
# 2) ⚠️ 必须人工审 alembic/versions/xxxx.py 的 upgrade()：
#    - 只含预期的 add_column / create_table，无 drop 列 / drop 表 / 破坏性删改
#    - 已有数据需默认值/回填时，先补 DEFAULT 再收紧约束
# 3) 本地验证（dev sqlite）
alembic upgrade head
alembic current     # 应显示新 revision (head)
# 4) 回归：跑相关接口/测试后再部署
```

### 4.2 生产执行（随部署包走，容器内执行）

```bash
# 部署包已含 alembic/（requirements.txt 已加 alembic+psycopg2-binary；
# Dockerfile 已 COPY alembic.ini + alembic/ 进镜像 —— 重建后容器自带）
# 1) 备份（任何 DDL 前必做）
ssh ... "docker compose -f deploy/docker-compose.yml exec -T postgres pg_dump -U anchor -d anchor > /tmp/db-bak.sql"
# 2) 重建 backend 镜像后（内置 alembic），在容器内升级
ssh ... "sudo docker exec anchor-backend-1 sh -c 'cd /app && alembic upgrade head'"
# 3) 验证
ssh ... "sudo docker exec anchor-backend-1 sh -c 'cd /app && alembic current'"
#    → 显示本次新 revision (head) 即成功；否则回滚 `alembic downgrade -1` 并排查
# 4) 变更后：冒烟相关接口
```

> 注：容器内使用 compose 注入的 `ANCHOR_DATABASE_URL`（asyncpg），
> alembic/env.py 自动转为 sync psycopg2 连接——无需额外配 URL。
> 若镜像未重建（老镜像无 alembic）：`docker exec anchor-backend-1 pip install alembic psycopg2-binary`，
> 并把本地 `alembic/` + `alembic.ini` `docker cp` 进 `/app` 再执行（2026-09-02 落地同法）。

### 4.3 全新空环境（新库/CI/本地从零起）

```bash
alembic upgrade head    # baseline 内 create_all 幂等建表（29 业务表）
```

### 4.4 stamp（存量库接入 Alembic，仅标记不动 schema）

```bash
# 已在生产执行完成（2026-09-02，anchor-backend-1 容器内）：
# docker cp alembic* 进 /app → pip install alembic psycopg2-binary → alembic stamp head
# stamp 只写 alembic_version 表（=79ecd7bf22a0），不 CREATE/ALTER/DROP 任何业务表
alembic stamp head
```

## 五、踩坑记录（勿再犯）

| # | 坑 | 避免 |
|---|-----|------|
| 1 | `--force-recreate` 不重建镜像 → 代码不生效 | 必须 `--build` |
| 2 | 只 `up -d --build backend` → nginx 缺失（前端打不开）| 必须 `up -d`（全量）|
| 3 | DB 表缺列 → 500（push_enabled）| 上线前 `alembic upgrade head` + `alembic current` 核对版本，勿手工 ALTER |
| 4 | pydantic env_prefix=ANCHOR_ → 新 env 必须 `ANCHOR_` 前缀 | 加 env 时查 compose environment |
| 5 | 生产 dist 需本地 build 后部署（部署源码≠构建产物）| 前端改动：本地 `vite build` → tar dist → 部署 |
| 6 | AI_PROVIDERS_JSON env 覆盖代码厂商表 | 改厂商用代码（providers.py）不用 env JSON |
| 7 | 上传接口路径 = /api/v1/portfolio/holdings/upload（非 holdings/upload）| 查 router 前缀 |
| 8 | schema 手动 ALTER → 版本失控（push_enabled/report_review 两次线上 500）| 一律 Alembic：改 model → `revision --autogenerate` → 审 upgrade → `upgrade head` |
| 9 | 对存量库跑 `alembic upgrade head` 会执行 baseline DDL | 存量库只 `stamp head`；`upgrade head` 仅用于全新空库 |

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
