# 验证记录

验证日期：2026-09-22。Python 3.12；requests 2.32.5、lxml 6.1.1、supabase-py 2.31.0、pytest 9.1.1；隔离数据库引擎 PGlite 0.5.8。

## 官网 dry-run

执行命令（项目根目录）：

```bash
.venv/bin/python 情报收集模块/scripts/fetch_ukmto_incidents.py --dry-run --max-incidents 100
```

最终统计：

```json
{
  "started_at": "2026-09-22T15:40:25.646567+00:00",
  "finished_at": "2026-09-22T15:40:29.198732+00:00",
  "fetched_count": 61,
  "parsed_count": 61,
  "inserted_count": 0,
  "updated_count": 0,
  "unchanged_count": 0,
  "failed_count": 0,
  "database_failed_count": 0,
  "list_failed": false,
  "exit_code": 0
}
```

61 个唯一事件 ID，61 条具有来源明确提供的有效坐标，解析告警 0。这里写入计数为 0 是 dry-run 的预期行为；没有执行线上 Supabase 写入。

采集源是官网动态组件所用的皇家海军公开 JSON 接口。最初直接读取 HTML 曾遇到访问限制；取得页面后还发现其初始 `0 reports` 不能代表真实空列表。已增加动态组件检测及公开 feed 适配，相关真实页面快照纳入回归测试。

## Python 测试

```bash
.venv/bin/python -m pytest 情报收集模块/tests -q
```

结果：`72 passed`。包括：

- 文档要求的事件分类、Update、缺失编号/时间/坐标、未知类型、字段缺失、距离描述、哈希稳定性。
- 当前官网 HTML 动态占位识别、61 条真实 feed 解析、年度编号隔离、原始信息保留。
- 新增/重复/更新、单条失败隔离、dry-run 不触碰仓储、数据库异常传播和退出码。
- 超时/5xx 重试、4xx 不重试、限速、重定向域名限制、非 HTML 响应、配置与日志脱敏。

## 数据库验证

在内存中启动 PGlite PostgreSQL，创建模拟 Supabase 的 anon/authenticated/service_role 角色，执行交付的完整迁移 SQL，然后运行 `tests/test_database.mjs`。

已通过：

- 首次插入主表 1 行、历史 1 行；重复请求仍为 1/1。
- 内容变化更新主表并新增历史；重复旧版本不覆盖较新 Update。
- 延迟抓取不覆盖较新观察结果，旧版本仍保存历史。
- 强制历史插入失败时，主表的新增/更新一起回滚。
- 两个唯一约束均拒绝重复写入；时间字段为 timestamptz；空坐标和空发生时间可保存，非法/半对坐标被拒绝。
- 重复内容不改变 `updated_at`，只推进 `last_seen_at`。
- 两表 RLS 启用；anon/authenticated 无表读取及 RPC 执行权限；service_role 可执行采集。
- 将真实 fixture 经当前解析器输出的 61 条事件插入隔离数据库，再次执行，仍为 61 条事件、61 条对应历史，无重复。

可将 CLI dry-run 的 JSONL 作为数据库测试的第二个参数，以复现真实数据持久化检查：

```bash
python 情报收集模块/scripts/fetch_ukmto_incidents.py --dry-run > /tmp/ukmto-events.jsonl
UKMTO_PGLITE_MODULE=/tmp/ukmto-db-test/node_modules/@electric-sql/pglite/dist/index.js \
  node 情报收集模块/tests/test_database.mjs /tmp/ukmto-events.jsonl
```

## 尚未执行的部署验证

本次仅编写与本地验证脚本，没有选择或修改用户线上 Supabase 项目，因此尚未验证目标项目上的迁移部署、PostgREST RPC 可见性、网络连接和服务密钥权限。需要在目标环境执行迁移并配置服务端环境变量后，再执行正常采集及重复执行检查。

数据库并发保护由唯一约束与行锁实现；隔离引擎验证没有模拟多个独立网络客户端同时写入。没有引入前端、FastAPI 路由或生产定时任务。
