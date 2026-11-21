# 命令参考

所有命令成功时退出码 0，摘要写 stdout，错误写 stderr。

## 通用参数

成绩/考试/课表：

```text
--config PATH        配置文件路径
--year YEAR          覆盖学年起始年，如 2025
--semester CODE      学期代码：3 秋季、12 春季、16 夏季
--force-email        没有变化也发送邮件
--no-proxy           不使用环境变量代理
--no-interactive     不等待任何输入
--save-json          保存 JSON
--save-report        保存 HTML 报告
--save-ics           保存 ICS（仅 exams/schedule）
--output-dir DIR     输出目录
--verbose            更详细日志
```

空闲教室：

```text
--date YYYY-MM-DD            必填
--start HH:MM --end HH:MM    成对出现；省略表示不按时刻过滤
--campus all|nanhu|wenchang  默认 all
--building CODE              楼号代码，如 博1
--min-seats N --max-seats N  座位数闭区间
--lendable                   只看“可借用”教室
--limit N                    默认 50；0 表示全部（上限 5000）
```

学业情况：仅 `--config/--no-proxy/--no-interactive/--verbose`（累计数据，无学期参数）。

上课情况：

```text
--course VALUE      映射到 kch_id（课程内部 ID）
--teacher NAME      教师姓名
--room TEXT         场地，如 博1-A203
--weekday 1-7
--periods 1-2       不带“节”
--weeks 1           起始周
--limit N           默认 50；0 全部（上限 1000）
```

`--course/--teacher/--room` 至少一个，否则退出码 2；这是为了避免拉取全校 1 万多条排课。

## grades query

流程：读配置 → 建 client → 可达性检查 → 读 `state.json` → 复用 cookie 或登录 → 拉成绩列表 → 快照/对比 → 按需拉详情 → 文本摘要 → 按需邮件 → 原子写 state → 按需产物。

详情查询条件：`grades.include_details_on_change=true`，且出现变化、`--force-email` 或 `--save-report`。普通无变化查询不拉详情。

## exams query

拉取考试安排、对比快照、输出摘要；检测到变化或 `--force-email` 时可发邮件（可附 ICS）。

## schedule query

拉取个人课表（含未排课课程与节次时间），对比快照；可发邮件（附 ICS）。

## classrooms query

按日期/时刻查空闲教室。注意：

- 接口返回的列表**本身就是该时段空闲教室**；`sfkjy` 只是“是否可借用”，不要用它判断空闲。
- `--lendable` 才加服务端 `sfkjy=1` 过滤。
- 每页 500、最多 10 页；结果按校区→楼→层→教室排序后截断展示。
- 不写 state、不发邮件、不落盘。

## academic query

累计培养方案数据，不按学期过滤。输出：

- 统计时间、全部课程 GPA、学位课 GPA；
- 计划课程 总/通过/未通过/未修/在读，计划外 通过/未通过；
- 培养方案树：要求学分 / 已获学分 / 已满或未满（差额），最大 4 级缩进；
- 按课程性质的 GPA、加权平均分、获得学分。

统计接口失败时只降级“按课程性质”部分；总览与树不受影响。

## courses query

全校排课明细查询：

1. GET `viewFunc_cxDesignFuncPageIndex.html` 解析 `data-func_widget_guid`；
2. POST `funcData_cxFuncDataList.html` 分页拉取；
3. 输出课程、教师、星期/节次、周次、地点、人数、学分。

结果含教师姓名等公开排课信息，只做终端展示；不包含教工号、性别。`--course` 按接口契约映射到 `kch_id`，传纯课程号可能匹配不到。

## 产物文件名

启用输出后写入 `output/`（或 `--output-dir` / `output.output_dir`），按学期后缀：

| 内容 | 文件名 |
|---|---|
| 成绩 JSON | `grades_<yy><sp\|fa>.json` |
| 成绩 HTML | `grade_report_<yy><sp\|fa>.html` |
| 考试 JSON | `exams_<yy><sp\|fa>.json` |
| 考试 HTML | `exam_report_<yy><sp\|fa>.html` |
| 考试 ICS | `exam_schedule_<yy><sp\|fa>.ics` |
| 课表 JSON | `schedules_<yy><sp\|fa>.json` |
| 课表 HTML | `schedule_report_<yy><sp\|fa>.html` |
| 课表 ICS | `schedule_<yy><sp\|fa>.ics` |

`sp`=春季，`fa`=秋季，例：`grades_26fa.json`。
