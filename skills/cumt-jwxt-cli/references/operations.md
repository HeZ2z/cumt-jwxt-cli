# 运行、安全与故障排查

## 定时任务

```cron
*/30 * * * * cd /path/to/cumt-jwxt-cli && uv run cumt-jwxt grades query --config ./config.local.json --no-interactive
```

建议：

- 显式 `--config`、固定工作目录、`--no-interactive`。
- 跨学期边界显式传 `--year/--semester`。
- 同一配置目录不要并行跑多个写 state 的命令；锁冲突会退出码 1。
- 调度系统关注非零退出码；`--no-interactive` 保证不会挂起等输入。

## 代理

`JWXTClient` 默认 `trust_env=True`，读取 `http_proxy` / `https_proxy` / `all_proxy`；项目带 `socksio`，支持 SOCKS。

```bash
http_proxy=http://127.0.0.1:10808 https_proxy=http://127.0.0.1:10808 \
  uv run cumt-jwxt grades query --no-interactive
```

需要直连时 `--no-proxy`。教务站点是 HTTP-only；`https://jwxt.cumt.edu.cn` 可能超时，`http://.../jwglxt/` 返回 403 属正常目录拒绝，实际页面路径可用。

## 安全边界

不要提交、分享或写入公开内容：

- `config.local.json`、`config.json`（账号、密码、SMTP、可能的 API Key）
- `state.json*`（cookie、快照）
- `logs/`、`output/`、`temp/`、`data/`
- 验证码图片、原始教务响应、HAR、抓包文件

实现与日志约定：

- 验证码只在内存中识别；人工回退写 0600 临时文件并删除，`--no-interactive` 不进入。
- 日志脱敏 cookie/password/API Key/JSESSIONID/route；不要主动记录请求头、响应正文、账号。
- 邮件不包含账号、密码、cookie、验证码或原始响应。
- 上课情况会返回教师姓名等他人公开排课信息：仅终端展示，不写日志/文件，不建模工号、性别。
- 明文 HTTP 无法防止窃听/篡改，这是教务站点的现实限制。

## 报告和产物

默认只输出终端摘要，不落盘。启用后写到 `output/`：

- 成绩：`grades_<学期>.json`、`grade_report_<学期>.html`
- 考试：`exams_*.json`、`exam_report_*.html`、`exam_schedule_*.ics`
- 课表：`schedules_*.json`、`schedule_report_*.html`、`schedule_*.ics`

HTML 使用 Jinja2 自动转义；某门课详情失败只跳过该详情，不中断整体查询。

## 常见问题

### Configuration file not found

```bash
cp config.example.json config.local.json
uv run cumt-jwxt grades query --config ./config.local.json
```

### Missing required configuration: query.year / query.semester

显式传 `--year/--semester`，或设 `query.auto=true` 并清空两者。只给一个会报错。

### 网络检查失败 / 超时

- 是否在可访问教务的网络（校园网/VPN/代理）。
- 代理变量是否正确；试 `--no-proxy`。
- `http://jwxt.cumt.edu.cn/jwglxt/` 403 不代表不可用。

### 登录失败

- 学号/密码、验证码、账号是否被限制。
- 会话失效时程序会自动重登一次；连续失败先检查凭据。
- 登录成功可能表现为 `POST 302 → login_slogin → 302 → index_initMenu`，不要把“跳回登录页”直接当失败。

### Captcha recognition failed

- 本地 ddddocr 模型是否随依赖安装；非 TTY 或 `--no-interactive` 不会人工回退。
- 不要接入外部识别服务，也不要把验证码图片上传。

### 返回 HTML / 302 / HTTP 901

通常表示会话失效，程序会重登一次。仍失败时检查网络、账号状态与教务是否维护。

### state.json 损坏或锁冲突

- 损坏：备份后删除，下一次重建。
- 锁冲突：同一配置已有任务在跑；等待结束，或给不同任务使用不同配置目录。

### 邮件失败

退出码 6。检查 SMTP 主机/端口（当前使用 SMTP_SSL）、授权码、发件人是否被允许、收件人地址。发送失败不会保存“已通知”时间，下次仍会尝试（可能重复发送）。

### 学期解析回退日历

日志出现 `JWXT current term unavailable; using calendar scope` 时，说明教室页结构变化或读取失败。显式传 `--year/--semester` 可固定学期。
