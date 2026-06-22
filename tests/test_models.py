"""Model helper tests."""

from pathlib import Path

from cumt_jwxt_cli.models import OutputConfig


def test_output_config_resolve_dir_uses_explicit_directory() -> None:
    config = OutputConfig(
        save_json=False, save_report=False, save_ics=False, output_dir="~/exports"
    )

    assert (
        config.resolve_dir(Path("/tmp/config.local.json"))
        == Path("~/exports").expanduser()
    )


def test_output_config_resolve_dir_uses_config_adjacent_default() -> None:
    config = OutputConfig(
        save_json=False, save_report=False, save_ics=False, output_dir=""
    )
    config_path = Path("/tmp/project/config.local.json")

    assert config.resolve_dir(config_path) == Path("/tmp/project/output")
