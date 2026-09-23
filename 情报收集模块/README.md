# UKMTO 情报收集模块

按《海上情报平台模块.md》第一阶段实现：采集 UKMTO 事件、清洗、幂等写入 Supabase、保留更新历史。Python 3.10+。所有实现均位于本目录。

## 快速运行

以下命令在项目根目录执行，可直接使用项目已有的 `.venv/bin/python`：

```bash
python -m pip install -r 情报收集模块/requirements.txt
python 情报收集模块/scripts/fetch_ukmto_incidents.py --dry-run --max-incidents 20
```

`--dry-run` 不需要 Supabase 配置，也不初始化数据库客户端。解析结果以 JSON Lines 输出至 stdout，结构化日志和最终统计输出至 stderr。

正式入库前：

1. 在目标 Supabase 的 SQL Editor 执行 [数据库迁移](supabase/migrations/20260922153136_create_ukmto_incidents.sql)。这会新增两张表和一个事务 RPC；不要重复执行同一建表迁移。
2. 将 [.env.example](.env.example) 复制为本目录的 `.env`，填写 `SUPABASE_URL` 和 `SUPABASE_SERVICE_KEY`。也支持现有项目的 `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY` 别名。进程环境变量优先，然后读取本模块 `.env`、项目根目录 `.env`。
3. 执行：

```bash
python 情报收集模块/scripts/fetch_ukmto_incidents.py
python 情报收集模块/scripts/fetch_ukmto_incidents.py --max-incidents 20 --verbose
```

## 官网当前的实际数据路径

2026-09-22 验证发现，`/recent-incidents` 是 Next.js 动态页面，HTML 的 `0 reports` 是初始占位。脚本先请求列表页，识别其 `RecentIncident` 组件后，读取该官网组件使用的公开接口：

```text
https://sccd.royalnavy.mod.uk/api/ukmto/all
```

单次动态采集通常只需两个请求，不需要逐条打开页面。保留 HTML 详情页和锚点解析路径，以兼容静态页面。接口失败不会被当作空列表，也不会删除上次数据。

## GitHub Actions 定时采集

已提供 [UKMTO Reports Sync](../.github/workflows/ukmto-sync.yml)，每小时采集一次，最多处理 1000 条报告，支持手动运行和数据库失败后一次重试。

将工作流和完整模块提交到默认分支，并配置仓库 Actions Secrets 后启用。详细步骤见 [GitHub Actions 部署说明](docs/github-actions.md)。本地 `.env` 不会自动传到 GitHub。

## 测试

```bash
python -m pip install -r 情报收集模块/requirements-dev.txt
python -m pytest 情报收集模块/tests -q
```

另提供独立 PostgreSQL 引擎验证，不需要连接线上 Supabase。Node.js 20+，PGlite 仅为可选开发测试依赖：

```bash
npm install --prefix /tmp/ukmto-db-test --no-audit --no-fund @electric-sql/pglite@0.5.8
UKMTO_PGLITE_MODULE=/tmp/ukmto-db-test/node_modules/@electric-sql/pglite/dist/index.js \
  node 情报收集模块/tests/test_database.mjs
```

首次开发验证的官网 dry-run 解析了 61 条真实事件，0 条失败；单元测试与隔离数据库验证结果见 [验证记录](docs/verification.md)。随后在 2026-09-23 已完成目标 Supabase 的真实入库核对：61 条事件、61 条历史记录，无缺失。GitHub Actions 仍需按上述步骤启用。

目录职责、字段映射、定时运行、权限、退出码和二阶段 API 接入说明见 [运维与开发说明](docs/ukmto-recent-incidents-ingestion.md)。
