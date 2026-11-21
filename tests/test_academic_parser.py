"""Academic status page parser tests using synthetic fixtures."""

from cumt_jwxt_cli.academic.query_fetch import (
    parse_academic_overview,
    parse_academic_page,
    parse_plan_nodes,
)

_PAGE_HTML = """
<html>
  <body>
    <div id="alertBox">
      统计时间：2026-11-21 08:30　全部课程GPA：3.216 学位课GPA：3.05，
      计划课程 总：108 通过：75 未通过：0 未修：29 在读：4；
      计划外 通过：9 未通过：2
    </div>
    <input type="hidden" id="xh_id" value="20230001" />
    <div class="tree">
      <li xfyqjd_id='1' fxfyqjd_id=''>
        <span id='p1' yqzdxf='171.0' yxxf='148.5' sftg='0'>通识教育课程</span>
        <ul>
          <li xfyqjd_id='2' fxfyqjd_id='1'>
            <span id='p2' yqzdxf='45.0' yxxf='45.0' sftg='1'>通识教育必修课</span>
          </li>
          <li xfyqjd_id='3' fxfyqjd_id='1'>
            <span id='p3' yqzdxf='20.0' yxxf='10.0' sftg='0'>通识教育选修课</span>
          </li>
        </ul>
      </li>
      <li xfyqjd_id='4' fxfyqjd_id=''>
        <span id='p4' yqzdxf='--' yxxf=''>专业课程</span>
      </li>
      <li xfyqjd_id='5' fxfyqjd_id='99'>
        <span id='p5' yxxf='3.0'>孤儿课程</span>
      </li>
      <li xfyqjd_id='1' fxfyqjd_id=''>
        <span id='p1'>重复节点</span>
      </li>
    </div>
  </body>
</html>
"""


def test_parse_academic_overview_accepts_fullwidth_punctuation() -> None:
    overview = parse_academic_overview(
        "统计时间：2026-11-21 08:30　全部课程GPA：3.216 "
        "学位课GPA：3.05，计划课程 总：108 通过：75 未通过：0 "
        "未修：29 在读：4；计划外 通过：9 未通过：2"
    )

    assert overview.snapshot_at == "2026-11-21 08:30"
    assert overview.gpa_all == "3.216"
    assert overview.gpa_degree == "3.05"
    assert overview.plan_total == "108"
    assert overview.plan_passed == "75"
    assert overview.plan_failed == "0"
    assert overview.plan_unlearned == "29"
    assert overview.plan_in_progress == "4"
    assert overview.out_of_plan_passed == "9"
    assert overview.out_of_plan_failed == "2"


def test_parse_academic_overview_tolerates_missing_fields() -> None:
    overview = parse_academic_overview(
        "统计时间：2026/11/20 全部课程GPA：-- 计划课程 总：10 通过：3 未通过：1"
    )

    assert overview.snapshot_at == "2026/11/20"
    assert overview.gpa_all is None
    assert overview.gpa_degree is None
    assert overview.plan_total == "10"
    assert overview.plan_passed == "3"
    assert overview.plan_failed == "1"
    assert overview.plan_unlearned is None
    assert overview.plan_in_progress is None
    assert overview.out_of_plan_passed is None
    assert overview.out_of_plan_failed is None


def test_parse_plan_nodes_builds_parent_child_relationships() -> None:
    nodes = parse_plan_nodes(_PAGE_HTML)
    by_id = {node.node_id: node for node in nodes}

    assert list(by_id) == ["1", "2", "3", "4", "5"]
    assert by_id["1"].parent_id is None
    assert by_id["2"].parent_id == "1"
    assert by_id["3"].parent_id == "1"
    assert by_id["1"].name == "通识教育课程"
    assert by_id["2"].name == "通识教育必修课"
    assert by_id["1"].required_credits == "171.0"
    assert by_id["1"].earned_credits == "148.5"
    assert by_id["1"].is_passed is False
    assert by_id["2"].is_passed is True


def test_parse_plan_nodes_tolerates_missing_credits_and_status() -> None:
    nodes = parse_plan_nodes(_PAGE_HTML)
    by_id = {node.node_id: node for node in nodes}

    assert by_id["4"].required_credits is None
    assert by_id["4"].earned_credits is None
    assert by_id["4"].is_passed is None
    assert by_id["4"].name == "专业课程"


def test_parse_plan_nodes_keeps_orphans_and_drops_duplicates() -> None:
    nodes = parse_plan_nodes(_PAGE_HTML)
    by_id = {node.node_id: node for node in nodes}

    assert len(nodes) == 5
    assert by_id["5"].parent_id == "99"
    assert by_id["5"].earned_credits == "3.0"


def test_parse_academic_page_extracts_overview_tree_and_xh_id() -> None:
    overview, nodes, xh_id = parse_academic_page(_PAGE_HTML)

    assert overview.plan_total == "108"
    assert len(nodes) == 5
    assert xh_id == "20230001"


def test_parse_academic_overview_accepts_real_label_wording() -> None:
    overview = parse_academic_overview(
        "某同学,您的课程修读情况(供参考):( 统计时间 2026-11-21 08:30:00之前有效 ) "
        "当前所有课程平均学分绩点 (GPA): 2.58 "
        "当前学位课平均学分绩点 (GPA): 2.35 "
        "计划总课程 108 门 通过 75 门 , 未通过 0 门 ；未修 29 门 ； 在读 4 门 ！ "
        "计划外 : 通过 9 门 , 未通过 2 门"
    )

    assert overview.snapshot_at == "2026-11-21 08:30:00"
    assert overview.gpa_all == "2.58"
    assert overview.gpa_degree == "2.35"
    assert overview.plan_total == "108"
    assert overview.plan_passed == "75"
    assert overview.plan_failed == "0"
    assert overview.plan_unlearned == "29"
    assert overview.plan_in_progress == "4"
    assert overview.out_of_plan_passed == "9"
    assert overview.out_of_plan_failed == "2"


def test_parse_plan_nodes_handles_hex_ids_and_inline_js_names() -> None:
    page_html = """
    <li id='liA1' class='' fxfyqjd_id='' xfyqzjdgx=''>
      <div class='title' xfyqjd_id='A1'>
        <p class='title0' id='pA1' yxxf='45.0' yqzdxf='45' sftg='1'>" +
          "通识教育课程&nbsp;" + $.i18n.get('yqxf')/* 学分 */ + ":45.0" +
        "</p>
      </div>
    </li>
    """

    nodes = parse_plan_nodes(page_html)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.node_id == "A1"
    assert node.name == "通识教育课程"
    assert node.required_credits == "45"
    assert node.earned_credits == "45.0"
    assert node.is_passed is True
