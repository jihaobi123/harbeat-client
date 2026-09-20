from __future__ import annotations

from app.shared.command_line import split_command_line


def test_windows_command_preserves_backslashes_and_unquotes_paths() -> None:
    command = (
        r'"C:\Program Files\Python312\python.exe" '
        r'"C:\HarBeat workers\worker.py" "{audio}"'
    )

    assert split_command_line(command, windows=True) == [
        r"C:\Program Files\Python312\python.exe",
        r"C:\HarBeat workers\worker.py",
        "{audio}",
    ]


def test_windows_unquoted_command_does_not_consume_path_separators() -> None:
    command = r"C:\Python312\python.exe C:\harbeat\worker.py {audio}"

    assert split_command_line(command, windows=True) == [
        r"C:\Python312\python.exe",
        r"C:\harbeat\worker.py",
        "{audio}",
    ]


def test_posix_command_keeps_existing_shell_style_tokenization() -> None:
    command = '/usr/bin/python3 "/opt/harbeat workers/worker.py" "{audio}"'

    assert split_command_line(command, windows=False) == [
        "/usr/bin/python3",
        "/opt/harbeat workers/worker.py",
        "{audio}",
    ]
