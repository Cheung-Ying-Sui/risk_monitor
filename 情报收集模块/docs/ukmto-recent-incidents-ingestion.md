# UKMTO Recent Incidents 采集说明

## 实现范围

本模块实现第一阶段后端采集与持久化。未改动现有船舶采集、风险区、前端或 `api/main.py`。数据库仓储保留 `get()` 与 `list_incidents()`，供第二阶段 FastAPI 路由使用；当前不新增 HTTP 服务。

```text
ukmto/
  client.py           HTTP、受控重定向、超时、有限重试、限速
  parser.py           HTML / 官方 JSON 解析、坐标、时间、标识、哈希
  models.py           事件、抓取响应、运行统计
  config.py           环境变量与范围校验
  repository.py       Supabase RPC 写入、查询接口
  service.py          采集编排、逐条失败隔离、统计
  logging_utils.py    JSON 日志与敏感内容过滤
scripts/fetch_ukmto_incidents.py
supabase/migrations/20260922153136_create_ukmto_incidents.sql
tests/                 单元测试、真实 fixture、隔离数据库测试
```

## 数据来源与页面适配

起点：[UKMTO Recent Incidents](https://www.ukmto.org/recent-incidents)。真实页面通过 `__NEXT_DATA__` 中的 `componentName=RecentIncident` 识别，而不是依赖带随机后缀的 CSS 类名。官网生产脚本使用 [皇家海军公开事件接口](https://sccd.royalnavy.mod.uk/api/ukmto/all)。默认模式自动选择这个官方数据路径。

若列表页提供静态事件链接，则解析同域 HTML 详情或页面锚点。PDF、图片、非官方链接不会作为 HTML 详情抓取。未识别的页面结构、动态数据请求失败、HTTP 403/429 或访问挑战会明确报错；不会绕过验证码或自动切换代理。

只处理 `incidentIssuer=UKMTO` 的事件。动态接口记录按来源事件时间降序处理，再应用 `--max-incidents`。若事件总数超过限制，超出范围的旧事件更新需提高采集上限才能覆盖。

## 字段映射

| 内部字段 | 当前官方 JSON 来源与规则 |
| --- | --- |
| `external_id` | 优先公告编号和来源年份，例 `UKMTO-2026-141`；编号年度重置，包含年份避免跨年碰撞。年份取公告明确年份，否则事件时间、创建时间中的年份，绝不取抓取时钟。无法确定编号/年份时使用来源 URL 的 SHA-256。 |
| `incident_number` | 规范化年度编号，如 `141-2026`；完整原始编号保留在 `raw_payload.record`。 |
| `title` | 可识别的公告首行；否则使用官网界面的“事件类型 UKMTO #编号”形式。 |
| `description` | `otherDetails` 完整正文，清理多余空白但保留段落；原文完整存入 `raw_payload.record.otherDetails`。 |
| `incident_type` | `incidentTypeName` 映射为文档枚举；未识别为 `unknown`。 |
| `incident_time` | `utcDateOfIncident`，缺失为空。 |
| `published_at` | 当前接口只提供 `utcDateCreated`，用作来源记录发布时间；正文 Issue Date / Report Date 仍保留在原文，未混同为事件发生时间。 |
| `source_updated_at` | 当前接口没有明确更新时间，留空；HTML 路径可读取明确的更新标签或元数据。 |
| `location_text` | 优先正文的海里距离描述，否则 `place`。 |
| `latitude/longitude` | 只使用官方提供的明确坐标；校验数值范围和成对存在，不按距离推算。 |
| `location_precision` | 正文含距离描述时保守标注 `approximate`；仅有地区名、没有坐标时为 `region`；明确来源坐标且没有模糊描述时为 `exact`。这是采集分类，不保证官方定位误差。 |
| `region/vessel_type` | `region` / `vesselType`；不对海区代码进行无依据映射。 |
| `source_type` | 正文明确 Source 标签可映射为 master / military_authority 等；没有标签为 unknown。 |
| `verification_status` | 缺少明确来源核验状态时 unknown，不因为来自官网就填 verified。 |
| `casualties/environmental_impact` | HTML 路径提取明确字段；JSON 中只在正文出现时保留原文，不凭关键词推断结论。 |
| `source_url` | 官网实际使用的详情锚点：`/recent-incidents#sitecoreId`。 |
| `raw_payload` | 官方完整记录/HTML、解析版本、抓取时间、请求来源、告警和版权署名。 |

HTML 日期支持 ISO 8601、日/月/年、英文月份和带四位年份的 UKMTO DTG。无时区的明确日期按 UTC 处理；仅日期为当天 00:00 UTC；无法解析时留空并记录告警。HTML 编号支持 `UKMTO #141`、`Incident number: 2026/141` 等；完全缺失编号时对规范化 URL 取哈希，保留锚点、排除跟踪参数。

## 幂等、版本历史与中断恢复

仓储调用 `ingest_ukmto_incident`，由一个 PostgreSQL 事务执行以下操作：

1. 以 `(source, external_id)` 唯一约束插入，冲突时锁定已有行再比较。
2. 内容哈希相同只更新 `last_seen_at`，不改变 `updated_at` 或增加重复历史。
3. 内容变化更新当前行，按 `(incident_id, content_hash)` 保存唯一历史快照。
4. 晚到的较旧抓取、较早来源版本或较低 Update 编号保留历史，但不覆盖当前较新内容，统计归为 `unchanged`。
5. 主表或历史写入任一步失败，整个事务回滚。中断后重新执行可重试。

哈希覆盖规范化业务字段以及官方船名、被控制状态、扣押时间和扣押人数等原始事实，不包含抓取时间、HTML 排版或 UI ticker 开关。新事件的首个版本也保存历史。完整历史快照位于历史表的 `raw_payload.snapshot`，原始来源位于 `raw_payload.source_payload`。

表启用 RLS，撤销 `anon/authenticated/PUBLIC` 的访问，仅授予后端 `service_role` 所需权限。RPC 使用 `SECURITY INVOKER`，不增加越权能力。无需 PostGIS。本次只提供本地迁移，不自动修改已连接的生产数据库。

## 环境变量与请求策略

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `SUPABASE_URL` | 无 | 正式入库必填 |
| `SUPABASE_SERVICE_KEY` | 无 | 服务端密钥，支持项目已有的两个别名 |
| `UKMTO_REQUEST_TIMEOUT_SECONDS` | 30 | 每次请求超时，范围 (0, 300] |
| `UKMTO_REQUEST_RETRIES` | 3 | 初次请求之后最多追加重试次数，范围 0–5 |
| `UKMTO_MAX_INCIDENTS_PER_RUN` | 100 | 每次处理上限，范围 1–1000；CLI 参数优先 |
| `UKMTO_REQUEST_INTERVAL_SECONDS` | 1 | 相邻请求最小间隔，不能小于 1 秒 |
| `UKMTO_POLL_INTERVAL_MINUTES` | 10 | 计划周期配置；本脚本每次只运行一次，实际周期需同步设置 cron |
| `UKMTO_USER_AGENT` | RiskMonitor/0.1… | 明确标识客户端，可添加运维联系方式 |

仅连接错误、超时和 5xx 有限重试，等待 1、2、4…秒。4xx 立即失败，遵守站点访问限制。重定向最多 5 次，限定官方 UKMTO 域名或已核实的单个公开 feed 地址。

## 日志、统计和退出码

stdout：仅 dry-run 事件 JSON Lines。stderr：JSON 结构化日志。`--verbose` 额外输出事件哈希和位置精度，不打开 HTTP 头或 SDK debug 日志。

最终 `ukmto_fetch_finished` 包含开始/结束时间及 fetched、parsed、inserted、updated、unchanged、failed 计数。`fetched_count` 是取得内容的事件数，不是 HTTP 请求数。dry-run 的三个写入计数均为零；不要把它们当作数据库变化预测。

| 退出码 | 含义 |
| --- | --- |
| 0 | 任务完成，无失败 |
| 1 | 配置或参数错误 |
| 2 | 列表请求、列表结构或动态 feed 失败 |
| 3 | 至少一条数据库写入失败，优先于普通单条错误 |
| 4 | 单条请求/解析失败，但其余条目已继续处理 |

## 定时运行

先创建本模块的日志目录，再配置 cron。以下路径仅为示例，应替换为部署位置：

```bash
mkdir -p /path/to/risk_monitor/情报收集模块/logs
```

```cron
*/10 * * * * cd /path/to/risk_monitor/情报收集模块 && /path/to/risk_monitor/.venv/bin/python scripts/fetch_ukmto_incidents.py >> logs/ukmto.log 2>&1
```

无需进程内缓存、Celery 或本地去重文件。不要因为临时请求失败增加任务频率；为日志配置部署侧轮转。调整轮询环境变量不会自动安装或修改 cron。

## 第二阶段 API

仓储查询可由 FastAPI 调用：`get(external_id)`，以及 `list_incidents(from_time, to_time, incident_type, region, status, limit, offset)`；时间过滤目前针对 `published_at`，含边界，按发布时间降序及 ID 排序。

建议后续路由仍采用开发文档的三个路径；GeoJSON 使用 `[longitude, latitude]`，仅有效坐标生成点，无坐标事件仍显示在列表。后端应设置 API 访问策略，并过滤不需要向前端公开的原始 payload。不要在前端提供服务端密钥，也不要把事件点解释为实时 AIS 船位。

## 来源、许可和限制

来源为 UKMTO；保留来源链接与 `UKMTO / Crown copyright` 署名。官网 [Terms and Conditions](https://www.ukmto.org/terms-and-conditions) 说明内容按 Open Government Licence 提供，使用与再发布仍需遵循该许可和站点条款。测试 fixture 仅记录开发时公开返回的资料，不表示完整历史或实时数据。

公开 feed 并非承诺稳定的版本化 API；结构变化会报错，应结合新 fixture 更新适配。当前未实现 PDF/OCR、自动地名编码、实时船位、风险评分或任何前端页面。
