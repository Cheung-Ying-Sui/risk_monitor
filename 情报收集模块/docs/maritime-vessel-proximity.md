# 海事情报地图与船舶周边事件计数

## 接口与统计定义

`GET /api/v1/ukmto/vessel-risk-counts`

复用事件 API 的 `from`、`to`、`incident_type`、`region`、`status` 校验和仓储过滤。时间是 **published_at（UTC）**，非事件发生时间。无时间参数表示全部已收录事件，不自动表示“当前仍有效”。页面构造一个时间快照供事件列表分页和计数请求共同使用，避免近 7/30 天边界不一致。

返回 `items`：vessel_id、name、imo、mmsi、latest_position（latitude、longitude、observed_at）、calculation_status、radius_nm、event_count、event_ids。响应还含 calculated_at、filters、time_basis、ais_max_age_hours。传入的 limit/offset 不截断空间统计；仓储内部读取所有匹配事件页。

- 球面 Haversine：`d = 2 R asin(sqrt(sin²(Δφ/2) + cosφ₁ cosφ₂ sin²(Δλ/2)))`。
- `R = 6371.0088 / 1.852 NM`，`d <= 500 NM` 命中，1e-9 NM 浮点边界容差。
- UKMTO 按稳定 external_id 去重；非法/缺失坐标不计入。零经纬度本身不被视为缺失。
- AIS 超过 24 小时、未来超过 5 分钟或时间不可解析返回 position_stale；缺失/非法坐标返回 position_unavailable；两者 event_count 均为 null。
- 24 小时内只能解释为“最近有效 AIS 位置”，不是持续实时观测保证。

## 数据与权限

复用 InsuranceRepository.list_insured_vessels：仅 confirmed/covered、保单非 cancelled、航程保障未结束的船舶。船舶身份按既有 IMO 优先、已核实 MMSI 次之、无 IMO 才用名称的逻辑关联 active tracking。位置仅来自 tracking.latest_vessel_positions；前端不提交坐标。无已跟踪身份时返回不可计算。

core.vessels、tracking.tracked_vessels、tracking.latest_vessel_positions 分页/分批读取，非每船查询。事件每页 1000；最多 50000 个带坐标事件、5000000 次船舶/事件比较，超限或分页不完整返回 503，不返回部分计数。阶段间 25 秒 deadline，前端 30 秒请求超时；底层 SDK 单次 I/O 仍依赖现有客户端超时。大规模场景需再做数据库空间索引/专用批量查询，不无限扩大内存扫描。

沿用现有本地 API 权限和服务端 Supabase 凭据，未扩大数据库权限、未新增 migration。当前本地 API 没有新加独立认证层，不能直接作为公网多租户接口开放。

## 前端

- `category-icon.tsx` 固定 SVG 符号供地图、图例、列表、详情共用。事件标记和图例外框为正方形，保留类别颜色、严重程度样式、键盘和 aria-pressed。
- `lib/vessel-marker.ts` 与原船舶跟踪地图共用船体 helper 和 globals.css 的蓝色船形；有效 heading 优先、COG 次之、无值朝北。AIS 511 无效方向不采用。
- 版权信息保持展开，实际移除 summary 圆圈按钮，保留地图署名和有效地图控件。
- 计数正数显示徽标；船舶列表显示统计范围、AIS 时间、零命中/计算中/失败/过期状态。徽标仅在后端计算所用 AIS 与地图位置一致时显示。
- 使用现有 insured/live hooks 和 identity matcher；响应保险更新事件、跨窗口 storage、窗口 focus，并每分钟刷新。筛选切换以请求 key 隔离结果，立即清空旧计数，取消旧请求。
- 生产海事情报原本未引用 mock fixture，此次保持真实 API 流程并增加无可定位真实数据提示。没有删除测试 fixture，也没有删除数据库记录。
- 深浅主题、窄屏布局在既有 CSS 中扩展；不修改 AIS 采集、投保状态或航程结束规则。

## 验证（2026-10-13）

- Python 相关测试：81 passed。包含新增空间/API/动态投保关联测试、原 UKMTO API、船舶 API、保险投影、跟踪和航程生命周期测试。
- 新增前端 `scripts/test-maritime-proximity.cjs`：5 passed，覆盖 SVG/共享标记、真实服务分页筛选快照、状态和筛选切换旧结果隔离。
- 其他 4 个既有前端脚本：12 passed。
- `npx eslint src scripts/test-maritime-proximity.cjs` 通过。
- `npm run lint` 仍被既有 4 个 CommonJS 测试脚本的 27 条 no-require-imports 报错阻挡，本次未改动这些无关脚本或放宽全局 lint 规则。
- `npm run build` 通过。
- 实际开发 API 读库请求返回 HTTP 200、两艘已投保且具有有效 AIS 的船舶及计数；这是当次数据快照，不是固定结果。页面 HTTP 200。
- 浏览器工具打开页面失败（连接超时），尚未完成深浅主题/窄屏的浏览器目视与实际点击验收；代码/渲染测试不替代该验收。

当前仅统计 UKMTO 已收录、符合筛选且带有效坐标的事件，不覆盖所有全球风险；来源坐标可能为近似位置。计数不是航迹相交、途经记录、事故概率或安全结论。
