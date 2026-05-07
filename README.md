# cumt-jwxt-cli

`cumt-jwxt-cli` 是面向 CUMT 教务系统的 Python CLI 项目。

首个命令路径为：

```bash
cumt-jwxt grades query
```

当前已完成的能力：

- 标准 `src` 包结构、`pyproject.toml`、`uv` 工具链和 CLI 入口
- 配置加载、环境变量覆盖、最小运行状态读写
- 成绩列表 JSON 解析、快照比较、文本/HTML 报告生成
- HTTP 客户端、登录流程、OpenAI 兼容验证码识别、SMTP 邮件发送的边界层实现
- `grades query` 的最小闭环：网络检测 -> 登录 -> 查询成绩列表 -> 解析 -> 生成摘要/报告 -> 按需发信 -> 更新 `state.json`

当前仍未完成的能力：

- 交互式配置补全
- 详细成绩查询与并发抓取
- 会话复用与 901 失效恢复
- 更完整的公开使用文档和定时任务示例

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

## 当前行为

`uv run cumt-jwxt grades query --config ./config.local.json` 目前会执行：

1. 读取配置并初始化日志
2. 使用当前代理或直连设置检测 JWXT 是否可访问
3. 获取登录页和验证码
4. 通过 OpenAI 兼容接口识别验证码
5. 登录 JWXT，登录提交后的 302 跳转视为成功登录
6. 查询成绩列表 JSON
7. 解析成绩并生成快照
8. 输出纯文本摘要
9. 在启用通知且有变更或 `--force-email` 时发送 HTML 邮件
10. 将快照和查询时间写入配置文件旁的 `state.json`

默认不保存 JSON、HTML 报告或验证码图片。只有显式启用 `--save-json` 或 `--save-report` 时，才会写入输出目录。

## 邮件通知

邮件通知默认关闭。配置 `notify.enabled = true` 后，只有检测到成绩变化或显式传入 `--force-email` 时才发送。

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

## 安全说明

- 不要提交 `config.local.json`、`state.json`、日志、输出文件或任何真实运行产物。
- 不要在测试、日志或调试文件中保存账号、密码、cookie、session、API Key 或验证码图片。
- 当前日志实现包含基础敏感字段脱敏，但仍应避免主动记录敏感原始数据。
