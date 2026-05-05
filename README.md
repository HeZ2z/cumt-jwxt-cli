# cumt-jwxt-cli

`cumt-jwxt-cli` 是面向 CUMT 教务系统的 Python CLI 项目。当前仓库处于项目骨架阶段，只提供标准包结构、配置契约、命令入口和测试/lint 基础设施。

首个命令路径为：

```bash
cumt-jwxt grades query
```

> 业务功能尚未实现：登录、验证码识别、成绩查询、成绩解析和邮件通知会在后续阶段接入。

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

`config.local.json`、`state.json`、`logs/`、`output/`、`temp/` 和 `data/` 均不应提交到仓库。
