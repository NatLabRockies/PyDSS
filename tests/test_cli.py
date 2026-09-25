from typer.testing import CliRunner

from pydss.cli.pydss import cli


def test_cli_commands_are_registered():
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    for command in (
        "add-post-process",
        "add-scenario",
        "controllers",
        "convert",
        "create-project",
        "edit-scenario",
        "export",
        "extract",
        "extract-element-files",
        "reports",
        "run",
    ):
        assert command in result.output


def test_nested_cli_commands_are_registered():
    runner = CliRunner()

    for arguments, command in (
        (["controllers", "--help"], "reset-defaults"),
        (["convert", "--help"], "excel-to-toml"),
        (["edit-scenario", "--help"], "update-controllers"),
    ):
        result = runner.invoke(cli, arguments)
        assert result.exit_code == 0
        assert command in result.output
