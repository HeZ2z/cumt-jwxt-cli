# 配置参考

## 文件位置

未传 `--config` 时依次查找：

1. 当前工作目录的 `config.local.json`
2. 当前工作目录的 `config.json`
3. 源码 checkout 的项目根目录的 `config.local.json` / `config.json`

`config.example.json` 只作模板，永不作为默认运行配置。推荐：

```bash
cp config.example.json config.local.json
```

本地真实配置优先用 `config.local.json`；`config.json` 同样视为本地配置。两者都不要提交。

## 优先级

```text
命令行参数 > CUMT_JWXT_* 环境变量 > 配置文件 > 代码默认值
```

环境变量只覆盖部分字段：

| 环境变量 | 字段 |
|---|---|
| `CUMT_JWXT_USERNAME` | `cumt.username` |
| `CUMT_JWXT_PASSWORD` | `cumt.password` |
| `CUMT_JWXT_SMTP_HOST` | `notify.smtp_host` |
| `CUMT_JWXT_SMTP_USERNAME` | `notify.username` |
| `CUMT_JWXT_SMTP_PASSWORD` | `notify.password` |
| `CUMT_JWXT_SMTP_SENDER` | `notify.sender` |

## 查询学期

```json
"query": { "year": null, "semester": null, "auto": true }
```

优先级：

1. `--year` / `--semester`
2. 显式 `query.year` / `query.semester`
3. `query.auto=true` 且未配置：登录后读取教务当前学期
4. 教务读取失败：回退日历（9 月–次年 1 月秋季，2–8 月春季，1 月属上一学年秋季）
5. 仍无法确定：`ConfigError`

`year` 是学年起始年（`2026` 表示 2026–2027 学年）；`semester` 为 `3`（秋季）、`12`（春季）、`16`（夏季）。

`auto` 的教务来源是空闲教室页 hidden `#xnm/#xqm`；读不到不会中断查询，只回退日历。跨学期边界建议显式传参，避免学期切换被当成一次全量变化。

只给 `year` 或只给 `semester` 会报配置错误。

## 字段

`cumt`：`username`、`password`，必填。

`http`：`timeout_seconds`（默认 30）、`retry_attempts`（默认 2）、`retry_backoff_seconds`（默认 1.5）。

`grades`：`include_details_on_change`（默认 true）、`detail_concurrency`（默认 3）。

`captcha`：`manual_timeout_seconds`（默认 60）。验证码识别固定使用本地 ddddocr，模型随依赖提供；配置里遗留的 `provider` / `openai_compatible` 字段会被忽略。

`notify`：`enabled`（默认 false）、`smtp_host`、`smtp_port`（默认 465，SMTP_SSL）、`username`、`password`、`sender`、`sender_name`、`recipients`。

`logging`：`retention_days`（默认 14，最小按 1 天）。

`output`：`save_json`、`save_report`、`save_ics`、`output_dir`。`output_dir` 为空时写到配置文件旁的 `output/`。

## 交互式配置

配置不存在或必填字段为空、且 stdin 是 TTY 时，程序会提示补全并写回配置文件（会包含明文密码，注意权限）。

`--no-interactive` 或非 TTY：缺少配置直接失败，退出码 2。

## state.json

写在配置文件同目录，schema v5：

- `session_cookies`、`session_updated_at`
- `grade_queries` / `exam_queries` / `schedule_queries`：键为 `"<year>-<semester>"`，每项含 `snapshot`、`last_successful_query_at`、`last_notified_at`

不保存账号、密码、API Key、验证码或原始响应。cookie 仍属敏感信息，不要公开。

写入使用原子替换（`state.json.<pid>.tmp`）；查询期间持 `state.json.lock`，并发运行会快速失败。读取到旧 schema 会自动迁移并回写。

## 输出与日志

- 日志目录：配置文件旁 `logs/cumt-jwxt-YYYY-MM-DD.log`，按 `retention_days` 清理。
- 非 `--verbose` 下 httpx/httpcore 请求日志被压到 WARNING，CLI stderr 保持干净。
- 日志过滤器脱敏 `Cookie`、`Set-Cookie`、`password=`、`api_key=`、`JSESSIONID=`、`route=`、`cookie=`。
