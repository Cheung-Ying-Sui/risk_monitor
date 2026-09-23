# GitHub Actions 定时采集

工作流文件位于仓库根目录的 [`.github/workflows/ukmto-sync.yml`](../../.github/workflows/ukmto-sync.yml)，名称为 **UKMTO Reports Sync**。GitHub 只会从根目录 `.github/workflows/` 识别工作流，因此该文件没有放在模块子目录。

## 运行方式

- 每小时第 7 分钟触发，即每小时采集一次，避开整点。
- 支持在 Actions 页面使用 **Run workflow** 手动触发。
- 使用 Python 3.12，仅安装本模块 `requirements.txt` 中的依赖，并缓存 pip 下载。
- 每次处理最多 1000 条当前报告。数据库唯一约束和事务 RPC 负责新增、去重及保存更新历史，不仅查看最新一条报告。
- 同一工作流不并发执行，也不会自动中断正在运行的采集；单次作业最长 15 分钟。
- 如果脚本返回数据库错误（退出码 3），等待 30 秒重试整次任务一次；重复写入由现有幂等逻辑处理。再次失败时 Actions 标红。其他退出码保持失败，不无限重试。
- 不自动执行数据库迁移。数据库表和 RPC 应已部署；本会话已验证的目标 Supabase 已完成部署。

## 首次启用

### 1. 将代码提交到默认分支

仓库需要包含完整采集模块和工作流，不能只上传 `.yml`：

```text
.github/workflows/ukmto-sync.yml
情报收集模块/requirements.txt
情报收集模块/scripts/fetch_ukmto_incidents.py
情报收集模块/ukmto/*.py
```

推荐连同模块测试、迁移与说明一起提交。不要提交 `.env`；现有忽略规则已排除该文件。当前工作区还有其他功能的改动，应只选择本次 UKMTO 相关文件提交。

### 2. 配置仓库 Secrets

在 GitHub 仓库打开 **Settings → Secrets and variables → Actions → New repository secret**。

| Secret | 值 |
| --- | --- |
| `SUPABASE_URL` | 当前已验证的 Supabase 项目地址 |
| `SUPABASE_SERVICE_KEY` | 对应项目的服务端密钥 |

为兼容仓库现有工作流，也可以使用已有的 `SUPABASE_SERVICE_ROLE_KEY` 或 `SUPABASE_SECRET_KEY`。读取优先级为 `SUPABASE_SERVICE_KEY` → `SUPABASE_SERVICE_ROLE_KEY` → `SUPABASE_SECRET_KEY`；三个只需设置一个，并确保与 URL 属于同一个项目。

本地 `.env` 不会自动同步到 GitHub。此工作流关闭 dotenv 文件读取，数据库凭证仅通过采集步骤的环境变量注入；依赖安装步骤不接收服务端密钥。

### 3. 手动验证一次

在 **Actions → UKMTO Reports Sync → Run workflow** 中选择默认分支运行，查看 **Collect and persist UKMTO reports** 步骤的 JSON 日志。

正常结果应包含 `ukmto_fetch_finished`、`failed_count: 0` 和 `exit_code: 0`。已有的 61 条报告若没有变化，应计入 `unchanged_count`；官网新增报告会计入 `inserted_count`，内容更新会计入 `updated_count`。61 是此前验证时的数量，并非脚本固定数量。

## 后续维护

修改频率时编辑工作流 `schedule.cron`，不需要修改本地 `.env` 的 `UKMTO_POLL_INTERVAL_MINUTES`。当前设定每天计划触发 24 次，实际执行次数受调度影响。

GitHub 定时任务只从默认分支运行；繁忙时可能延迟或丢弃排队任务。公开仓库连续 60 天无活动时，定时工作流可能自动停用，需要重新启用。因此这里提供的是周期采集，不保证严格实时。见 [GitHub 官方 schedule 说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

若运行出现 `403/429`，查看来源访问限制，不要增加频率或绕过限制；若出现数据库错误，检查 Secret 所属项目、连接状态及已部署迁移。工作流失败会保留此前成功入库的数据。
