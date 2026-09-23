# Fixture 来源

- `attack.html`、`list.html`：人工构造，用于字段缺失、日期、坐标和静态 HTML 回归测试，不是真实公告。
- `recent_incidents_live.html`：2026-09-22 15:35:59 UTC 从 https://www.ukmto.org/recent-incidents 获取的真实 HTML，保留 Next.js 元数据，验证其“0 reports”为动态占位。
- `incidents_live.json`：2026-09-22 从 https://sccd.royalnavy.mod.uk/api/ukmto/all 获取的 61 条公开 UKMTO 记录，仅重新格式化 JSON。该地址来自官网公开生产脚本 `401-6f01fb41d1016b07.js` 的 RecentIncident 组件及生产 API 基础地址配置。

来源：UKMTO / Crown copyright。使用遵循 https://www.ukmto.org/terms-and-conditions 及其引用的 Open Government Licence。快照仅用于离线测试，不代表实时情报。
