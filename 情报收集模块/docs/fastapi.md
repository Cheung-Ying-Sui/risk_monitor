# UKMTO 查询 API

现有 `api/main.py` 已注册 UKMTO router。新增实现位于 `情报收集模块/ukmto/api.py`、`api_schemas.py`、`query_repository.py`。采集工作流与数据库结构不变，无需新增迁移。

## 启动

在项目根目录执行：

```bash
.venv/bin/python -m pip install -r requirements.txt -r 情报收集模块/requirements-api.txt
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000/docs ，查看 `ukmto` 分组并测试接口。API 服务需要独立运行；GitHub Actions 每小时更新数据库，不负责持续托管 FastAPI。

UKMTO 客户端按进程环境变量 → 模块 `.env` → 根目录 `.env` 的优先级读取 Supabase 配置，支持原有三个密钥别名。客户端首次请求时创建，配置变更后重启 API。主应用其他模块沿用其原有环境加载机制；建议部署时使用进程环境变量统一指定项目。凭证保留在后端，前端只访问 FastAPI。

## 三个 GET 接口

| 路径 | 作用 |
| --- | --- |
| `/api/v1/ukmto/incidents` | 列表，包含无坐标事件 |
| `/api/v1/ukmto/incidents/{external_id}` | 单条详情，如 `UKMTO-2026-141`；不存在返回 404 |
| `/api/v1/ukmto/incidents.geojson` | GeoJSON FeatureCollection，只包含有效坐标的事件 |

列表和地图接受同一组参数：

| 参数 | 语义 |
| --- | --- |
| `from` / `to` | 按 `published_at` 筛选，包含边界；ISO 日期或时间，无时区按 UTC。仅日期对应当天 00:00，要包含一天全部时间需指定当天结束时刻。 |
| `incident_type` | attack / suspicious_activity / hijack / advisory / military_interaction / unknown |
| `region` | 原值精确匹配，例如当前数据中的 `IO` |
| `status` | 原值精确匹配，如 `active`；不传时返回全部状态 |
| `limit` | 默认 100，最小 1，最大 1000 |
| `offset` | 默认 0，最小 0 |

按发布时间倒序、外部 ID 升序稳定排序，空发布时间排后。无发布时间的事件在未设置时间过滤时仍会返回。

```bash
curl 'http://127.0.0.1:8000/api/v1/ukmto/incidents?limit=20&offset=0'
curl 'http://127.0.0.1:8000/api/v1/ukmto/incidents?incident_type=attack&region=IO'
curl 'http://127.0.0.1:8000/api/v1/ukmto/incidents/UKMTO-2026-141'
curl 'http://127.0.0.1:8000/api/v1/ukmto/incidents.geojson?limit=1000'
```

## 列表与详情响应

列表格式如下；`items` 中每条事件的格式与详情接口一致：

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0,
  "has_more": false,
  "next_offset": null
}
```

事件字段包括编号、分类、标题、完整描述、发生/发布时间、来源更新时间、采集观察时间、位置文本、经纬度、位置精度、区域、船型、来源类型、核验状态、伤亡/环境影响、来源 URL 和状态。缺失值为 null。原始 HTML/JSON、内容哈希和内部数据库 ID 不向前端返回。

`total` 是应用所有筛选条件后的数量，不是当前页条数。用 `next_offset` 请求下一页，直到 `has_more=false`；不要假设源报告数量始终为 61，也不要只取第一页。多页之间如果采集产生更新，排序位置可能变化，前端可按 `external_id` 去重并定期刷新。

## 地图响应

响应 Content-Type 为 `application/geo+json`：

```json
{
  "type": "FeatureCollection",
  "features": [],
  "pagination": {
    "total": 0,
    "limit": 100,
    "offset": 0,
    "has_more": false,
    "next_offset": null
  }
}
```

每个 Feature 的 `id` 是外部事件 ID，`geometry.type` 为 `Point`，`geometry.coordinates` 按 **[longitude, latitude]** 排列。`properties` 包含事件公开字段，可用于地图点击详情和来源链接。

地图在数据库层先排除空坐标和范围外坐标，再进行分页与计数；其 `pagination.total` 仅表示可定位事件。列表总数可能比地图总数多，这是预期行为。保留 `(0, 0)` 等合法坐标，不使用真假值判断经纬度。`location_precision=approximate` 必须按近似位置呈现，事件点不是船舶实时位置。

前端获取全部地图分页的示例：

```javascript
const API_BASE = 'http://127.0.0.1:8000';

async function loadIncidentMap() {
  const byId = new Map();
  let offset = 0;
  while (true) {
    const response = await fetch(
      `${API_BASE}/api/v1/ukmto/incidents.geojson?limit=1000&offset=${offset}`
    );
    if (!response.ok) throw new Error(`UKMTO API: ${response.status}`);
    const page = await response.json();
    for (const feature of page.features) byId.set(feature.id, feature);
    if (!page.pagination.has_more) break;
    offset = page.pagination.next_offset;
  }
  return { type: 'FeatureCollection', features: [...byId.values()] };
}
```

现有主应用 CORS 已允许 `http://localhost:3000` 与 `http://127.0.0.1:3000`。部署到其他前端域名时需在主应用配置中添加实际域名。

## 错误与验证

- 422：非法类型、时间、分页范围，或 from 晚于 to。
- 404：事件 ID 不存在。
- 503：数据库配置、连接、查询或返回数据不可用；响应及日志不包含 SDK 原始异常中的凭证。

接口只读 Supabase，不会在 HTTP 请求期间触发抓取或执行数据库写入。测试通过依赖替换使用假仓储，不依赖生产凭证：

```bash
.venv/bin/python -m pytest 情报收集模块/tests tests/test_api_*.py -q
```

参考：[FastAPI 参数验证](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)、[Supabase select/count 与分页](https://supabase.com/docs/reference/python/select)。

2026-09-23 使用现有 `api.main` 的 HTTP 测试客户端直连已配置 Supabase 进行只读验证：列表 200 / 61 条，详情 200 且与列表一致，GeoJSON 200 / 61 个点，经纬度顺序正确；Attack 筛选总数 42。此数量是验证时快照，不是固定返回值。尚未部署常驻 API 服务或修改前端页面。
