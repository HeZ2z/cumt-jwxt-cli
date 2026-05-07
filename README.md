# cumt-jwxt-cli

`cumt-jwxt-cli` 是面向 CUMT 教务系统的 Python CLI 项目。

首个命令路径为：

```bash
cumt-jwxt grades query
```

当前已完成的能力：

- 标准 `src` 包结构、`pyproject.toml`、`uv` 工具链和 CLI 入口
- 配置加载、环境变量覆盖、最小运行状态读写
- 成绩列表 JSON 解析、详情 HTML 解析、快照比较、文本/HTML 报告生成
- HTTP 客户端、登录流程、OpenAI 兼容验证码识别、SMTP 邮件发送的边界层实现
- 基础 session 复用与会话失效回退登录
- 仅在有变更或 `--force-email` 时抓取详细成绩构成，并合入 HTML 报告
- `grades query` 的最小闭环：网络检测 -> 尝试复用 session 查成绩 -> 失效时登录 -> 查询/按需抓详情/报告/通知 -> 更新 `state.json`

当前仍未完成的能力：

- HTML 模版和样式优化

## 安装与验证

```bash
uv sync
uv run cumt-jwxt --help
uv run cumt-jwxt grades --help
uv run cumt-jwxt grades query --help
uv run python -m cumt_jwxt_cli --help
uv run pytest
uv run ruff check .
```

## 配置

复制示例配置后再填写本地敏感信息：

```bash
cp config.example.json config.local.json
```

配置优先级：

```text
CLI 参数 > CUMT_JWXT_* 环境变量 > config.local.json > 默认值
```

`config.local.json`、`state.json`、`logs/`、`output/`、`temp/` 和 `data/` 均不应提交到仓库。

交互模式下，如果 `config.local.json` 缺失或缺少必要字段，CLI 会按 `config.example.json` 的结构提示补全并写回配置文件；`--no-interactive` 或非 TTY 环境下仍会快速失败。

## 当前行为

`uv run cumt-jwxt grades query --config ./config.local.json` 目前会执行：

1. 读取配置并初始化日志
2. 使用当前代理或直连设置检测 JWXT 是否可访问
3. 优先使用 `state.json` 中保存的受控 session cookie 直接查询成绩
4. 如果会话失效，再获取登录页和验证码
5. 通过 OpenAI 兼容接口识别验证码
6. 如果自动识别失败且当前是交互式终端，临时写出验证码图片并等待人工输入
7. 登录 JWXT，登录提交后的 302 跳转视为成功登录
8. 重新查询成绩列表 JSON
9. 解析成绩并生成快照
10. 在启用 `grades.include_details_on_change` 且有变更或 `--force-email` 时抓取详细成绩构成
11. 输出纯文本摘要
12. 在启用通知且有变更或 `--force-email` 时发送 HTML 邮件
13. 将 session、快照和查询时间写入配置文件旁的 `state.json`

默认不保存 JSON、HTML 报告或验证码图片。只有显式启用 `--save-json` 或 `--save-report` 时，才会写入输出目录。

`state.json` 会保存受控 session cookie 以便后续运行复用，但不会保存账号、密码、API Key、验证码图片或原始响应正文。

如果手动删除或修改 `state.json` 中的 `JSESSIONID`、`route` 等 cookie，下一次查询会先尝试复用剩余 session；会话失效后会清空旧 cookie、重新登录并刷新 cookie。教务系统可能同时下发同名不同 path 的 cookie，CLI 会保存可序列化的最新同名 cookie 快照，不会因为同名 cookie 冲突而中断。

当前 HTML 报告在拿到详细成绩时会追加成绩构成区块；若单门详情查询或解析失败，会退化为只发送成绩列表，不中断整体查询。

验证码自动识别失败时，交互模式会把验证码图片写入系统临时文件，终端显示临时路径，并在 `captcha.manual_timeout_seconds` 内等待输入。输入完成、超时或失败后会清理临时文件。非交互环境不会等待人工输入，会直接失败，避免定时任务卡住。

## 保存产物

默认情况下，查询结果只用于当前终端输出、邮件通知和 `state.json` 更新，不会额外保存 JSON 或 HTML 文件。

如需保存查询结果：

```bash
uv run cumt-jwxt grades query --save-json --save-report --output-dir ./output
```

这会在 `output_dir` 下写入：

- `grades.json`
- `grade_report.html`

未显式指定 `--output-dir` 时，会默认写到配置文件同目录下的 `output/`。

## 定时任务示例

适合 cron 的最小命令：

```bash
cd /path/to/cumt-query-score
uv run cumt-jwxt grades query --config ./config.local.json --no-interactive
```

示例 cron：

```cron
*/30 * * * * cd /path/to/cumt-query-score && uv run cumt-jwxt grades query --config ./config.local.json --no-interactive
```

建议在定时任务里始终使用：

- 显式 `--config`
- `--no-interactive`
- 固定工作目录

这样可以避免因为 TTY、路径或默认配置探测差异导致任务行为不稳定。

## 邮件通知

邮件通知默认关闭。配置 `notify.enabled = true` 后，只有检测到成绩变化或显式传入 `--force-email` 时才发送。

`notify.username` 是 SMTP 登录账号，`notify.sender` 是邮件 `From` 地址。多数 SMTP 服务要求两者一致或要求 `sender` 是账号下已验证的别名。`notify.sender_name` 是可选显示名，例如：

```json
{
  "notify": {
    "username": "sender@example.com",
    "sender": "sender@example.com",
    "sender_name": "cumt-jwxt-cli"
  }
}
```

配置后收件人看到的发件人会类似 `cumt-jwxt-cli <sender@example.com>`。

SMTP 失败会输出分类后的安全错误信息：

- `SMTP authentication failed`：检查 SMTP 用户名、密码或授权码。
- `SMTP connection failed`：检查 SMTP 主机、端口、网络可达性和 TLS 设置。
- `SMTP send failed`：检查发件人、收件人和服务商发送策略。

邮件发送失败时不会更新成绩快照，便于下次运行继续尝试通知。

## 代理说明

- 默认情况下，`cumt-jwxt grades query` 会使用系统环境变量里的代理设置。
- 如果 JWXT 需要直连，使用：

```bash
uv run cumt-jwxt grades query --no-proxy
```

- 项目已包含 `socksio` 依赖，用于支持通过 SOCKS 代理访问 JWXT。

## 常见故障

- `Configuration file not found`
  - 先复制 `config.example.json` 为 `config.local.json`
  - 或显式传入 `--config /path/to/config.local.json`

- `Missing required configuration`
  - 交互模式下重新运行并补全缺失字段
  - 自动化运行时检查 `config.local.json` 和 `CUMT_JWXT_*` 环境变量

- `JWXT network check failed` / `timed out`
  - 检查当前网络是否能访问 `jwxt.cumt.edu.cn`
  - 检查系统代理是否可用
  - 如需直连，使用 `--no-proxy`

- `JWXT login failed`
  - 检查学号、密码和验证码识别配置
  - 若已有 `state.json`，确认其中会话是否过期并允许程序重新登录

- `SMTP authentication failed`
  - 检查 `notify.username`、`notify.password`
  - 某些服务商需要授权码而不是邮箱登录密码

- 邮件发件人显示不符合预期
  - `notify.sender` 是邮箱地址
  - `notify.sender_name` 是显示名
  - 某些服务商会强制改写 `From`

## 免责声明

本项目仅用于个人自动化查询本人教务成绩信息。使用者应自行确保：

- 遵守学校教务系统使用规范
- 控制查询频率，避免对教务系统造成不必要压力
- 妥善保管本地配置、状态文件和邮件账号凭据

项目默认遵循“最小必要保存”原则，但本地运行环境、邮件服务商和代理环境仍可能引入额外风险，使用前应自行评估。

## 安全说明

- 不要提交 `config.local.json`、`state.json`、日志、输出文件或任何真实运行产物。
- 不要在测试、日志或调试文件中保存账号、密码、cookie、session、API Key 或验证码图片。
- 当前日志实现会脱敏密码、API Key、JSESSIONID、route 以及 `Cookie`/`Set-Cookie` 头，但仍应避免主动记录敏感原始数据。
