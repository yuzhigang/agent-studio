import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "src.runtime.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "run-inline" in result.stdout
    assert "supervisor" in result.stdout
