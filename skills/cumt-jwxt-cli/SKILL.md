---
name: cumt-jwxt-cli
description: >
  Use when operating or developing cumt-jwxt-cli, the CUMT JWXT command line
  tool: querying grades, exams, personal schedule, free classrooms, academic
  progress, or course sessions; configuring accounts, SMTP, captcha, or term
  detection; running it from cron/launchd; or debugging login, captcha,
  state.json, reports, and proxy issues.
license: MIT
---

# cumt-jwxt-cli

面向中国矿业大学教务系统（JWXT）的 Python CLI。默认只读，适合手动查询或定时任务。

## 何时使用

- 查询本人成绩、考试、课表，或检测变化并邮件通知。
- 按日期/时段查空闲教室；按课程/教师/场地查上课情况。
- 查累计学业情况：GPA、培养方案学分、按课程性质统计。
- 配置账号、SMTP、代理、验证码或查询学期。
- 排查登录、验证码、`state.json`、报告、定时任务问题。
- 修改本仓库代码或测试。

## 安装与入口

```bash
uv sync
uv run cumt-jwxt --help
```

也可 `pip install .` 或 `pip install -e .`。命令名为 `cumt-jwxt`，Python 3.11+。

## 命令总览

| 命令 | 用途 | 是否写 `state.json` |
|---|---|---|
| `cumt-jwxt grades query` | 成绩列表、变化检测、可选邮件/报告 | 是 |
| `cumt-jwxt exams query` | 考试安排、变化检测、可选 ICS | 是 |
| `cumt-jwxt schedule query` | 个人课表、变化检测、可选 ICS | 是 |
| `cumt-jwxt classrooms query --date YYYY-MM-DD` | 空闲教室 | 否 |
| `cumt-jwxt academic query` | 累计学业情况 | 否 |
| `cumt-jwxt courses query (--course ID \| --teacher NAME \| --room TEXT)` | 全校上课情况，必须带一个标识过滤 | 否 |

所有查询子命令共享：`--config PATH`、`--no-proxy`、`--no-interactive`、`--verbose`；除 `academic` 外均支持 `--year/--semester`（`classrooms`、`courses` 也支持）。

常用示例：

```bash
uv run cumt-jwxt grades query --config ./config.local.json
uv run cumt-jwxt exams query --save-ics
uv run cumt-jwxt schedule query --no-interactive
uv run cumt-jwxt classrooms query --date 2026-11-23 --start 08:00 --end 09:40 --campus nanhu
uv run cumt-jwxt courses query --room 博1-A203 --limit 20
uv run cumt-jwxt academic query
```

完整参数与输出：`references/commands.md`。

## 配置与查询学期

配置文件按顺序查找当前目录、项目根目录下的 `config.local.json`、`config.json`；`config.example.json` 只是模板。`--config` 显式指定。

敏感字段可用环境变量覆盖：`CUMT_JWXT_USERNAME`、`CUMT_JWXT_PASSWORD`、`CUMT_JWXT_SMTP_HOST/USERNAME/PASSWORD/SENDER`。

学期优先级：

1. `--year` / `--semester`
2. 配置文件显式 `query.year` / `query.semester`
3. `query.auto=true` 且未配置：登录后读取教务当前学期
4. 教务读取失败：回退日历推导
5. 仍无法确定：配置错误，退出码 2

`query.auto=true` 时把 `year`、`semester` 设为 `null` 或省略。跨学期边界建议显式传参，避免把学期切换当成全量变更。

细节：`references/configuration.md`。

## 运行行为

- 查询前检查教务可达性；复用 `state.json` 中的 cookie，会话失效时重登一次。
- 验证码使用本地 `ddddocr`，图片不出本机；识别失败且处于交互式终端时可人工输入。
- `--no-interactive` 下不等待任何输入：配置缺失或验证码失败快速退出。
- 代理默认读取环境变量（`trust_env`）；`--no-proxy` 直连。
- 写 `state.json` 的命令使用进程级锁 `state.json.lock`；同一配置并发运行会快速失败。
- 常规运行不把 httpx 请求日志打到 stderr；`--verbose` 才显示更详细日志。

## 输出与退出码

- 成功摘要写 stdout，错误写 stderr。
- 成绩/考试/课表可选保存 JSON/HTML/ICS，文件名带学期后缀（如 `grades_26fa.json`、`exam_schedule_26fa.ics`）。
- 空闲教室、学业情况、上课情况只输出终端文本，不落盘。

退出码：

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 未分类错误、状态/快照错误、并发锁冲突 |
| 2 | 配置或参数错误 |
| 3 | 登录或验证码错误 |
| 4 | 教务查询/网络错误 |
| 5 | 解析错误 |
| 6 | 邮件通知错误 |

## 安全边界

不得提交或公开：`config.local.json`、`config.json`、`state.json*`、`logs/`、`output/`、账号、密码、API Key、cookie/session、验证码图片、原始教务响应、HAR。

- `state.json` 保存 cookie 与按学期快照，不保存账号密码。
- 日志过滤器脱敏 cookie/password/API key/JSESSIONID/route，但仍不要主动记录响应正文。
- 上课情况会返回教师姓名等他人信息：仅终端展示，不写日志/文件。
- 教务站点目前是 HTTP-only，cookie 明文传输是残余风险；不要把它当作安全通道。
- 手工验证码模式会在系统临时目录写 0600 临时图片，流程结束删除。

更多：`references/operations.md`。

## 故障排查速查

| 现象 | 先查 |
|---|---|
| `Configuration file not found` | 复制 `config.example.json` 或传 `--config` |
| `Missing required configuration: query...` | 显式给 `--year/--semester`，或设 `query.auto=true` |
| 网络检查失败/超时 | 校园网、代理、`--no-proxy`；`/jwglxt/` 403 是正常目录拒绝 |
| 登录失败 | 密码、验证码、账号锁定；`state.json` 中 cookie 是否过期 |
| 验证码失败 | 本地 ddddocr 模型；非 TTY 下不会人工回退 |
| 查询返回 HTML/302 | 会话失效，程序会重登一次；仍失败查网络/账号 |
| `state.json` 损坏 | 备份后删除，下一次会重建 |
| 并发锁冲突 | 同一配置已有任务在跑；等待或拆分配置目录 |
| 邮件失败 | SMTP 主机/端口/授权码/发件人；退出码 6 |

详细：`references/operations.md`。

## 开发

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
```

分层：`cli` 只做参数/输出/编排；`client` 负责 HTTP、登录、学期；各 domain（`grades/exams/schedule/classrooms/academic/courses`）负责抓取、解析、快照/报告；`state` 负责原子读写与锁。测试必须 mock 教务、OCR、SMTP。

约定与结构：`references/development.md` 和根目录 `AGENTS.md`。
