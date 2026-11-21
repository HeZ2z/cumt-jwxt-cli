# 开发约定

## 工具链

- Python 3.11+
- `uv` 管理依赖、虚拟环境和锁文件
- `pytest`
- `ruff`（lint + format，行宽 88，目标 py311）

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
```

修改依赖用 `uv add` / `uv add --dev`，并提交 `pyproject.toml` 与 `uv.lock`。不要用 `pip install`、Poetry、Pipenv 改依赖。

## 项目结构

```text
src/cumt_jwxt_cli/
  cli.py                 参数解析、错误映射、终端输出
  config.py              配置加载、交互式补全
  errors.py              异常类型与退出码
  logging_config.py      日志与脱敏
  models.py              dataclass 模型
  state.py               state.json 读写、schema 迁移、并发锁
  time_utils.py          ISO 时间、日历学期推导
  app/session.py         会话复用、重登一次、学期解析
  client/                HTTP、登录、RSA、当前学期、分页
  captcha/               ddddocr 与人工回退
  grades/                成绩抓取、解析、快照、报告、通知
  exams/                 考试安排、ICS
  schedule/              个人课表、ICS
  classrooms/            空闲教室
  academic/              学业情况（HTML 解析）
  courses/               全校上课情况（guid + POST）
  notify/                SMTP
tests/                   pytest，全部 mock 外部服务
skills/cumt-jwxt-cli/    项目内 agent skill（本文件所在目录）
```

## 分层

- `cli` 只做参数、输出、错误映射和流程编排，不解析 HTML、不发底层请求。
- `client` 负责 HTTP、登录、会话、当前学期和分页；`ensure_authenticated_response` 统一识别 901/3xx/HTML 登录页。
- 各 domain 负责抓取、解析、快照、报告；不得依赖 CLI。
- `app/session.py` 用 `_with_session()` 统一“建 client → 复用 cookie → 失效重登一次 → 按需解析学期”，新增查询应复用它，不要复制会话逻辑。
- 写 `state.json` 的命令在 CLI 层加 `state_lock`；只读命令不写 state。
- 业务模型用 frozen dataclass；缺失字段显式 `None`，不用魔法字符串。

## 测试

- 新增/修改业务逻辑必须同步测试。
- 测试不得访问真实教务、OCR 服务或 SMTP；HTTP/登录/解析全部 mock。
- fixture 不得含真实账号、密码、cookie、学号、姓名、验证码、完整响应或 HTML。
- CLI 行为至少覆盖 `--help`、参数校验、主要错误路径。
- 提交前：`uv run ruff check .` + `uv run pytest`；格式化用 `uv run ruff format .`。

## 安全

测试、日志、注释、示例中不得出现真实账号、密码、API Key、cookie、session、验证码或教务响应。新增日志前确认不会泄露请求头、cookie、响应正文或他人信息。

## 新功能检查清单

1. 接口是否只读？写/导出/打印端点必须避开。
2. 是否复用 `_with_session` 与 `ensure_authenticated_response`？
3. 是否需要 `state.json`？只读功能不要写。
4. 分页是否读取 `totalResult`、避免越界页与静默截断？
5. 输出是否默认终端、仅显式启用时才落盘？
6. 是否新增了 PII 字段？日志/模型/报告中是否必要？
7. 是否补了 mock 测试与 `--help`/参数/错误路径覆盖？

## 文档维护

使用与开发说明放在本 skill 内：

- `SKILL.md`：入口、命令总览、优先级、安全、故障速查
- `references/commands.md`
- `references/configuration.md`
- `references/operations.md`
- `references/development.md`

改 CLI 参数、配置字段、输出命名或错误码时同步更新对应文件，避免文档与实现漂移。
