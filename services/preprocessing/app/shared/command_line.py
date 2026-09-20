"""Cross-platform parsing for configured subprocess command templates.

HarBeat stores a few optional worker commands in environment variables.  The
commands are executed with ``shell=False``, so parsing must preserve Windows
backslashes instead of applying POSIX shell escaping rules.
"""
from __future__ import annotations

import os
import shlex


def split_command_line(command_line: str, *, windows: bool | None = None) -> list[str]:
    """Split one configured command into argv without invoking a shell.

    ``shlex.split`` defaults to POSIX behavior and turns a path such as
    ``C:\\Users\\name`` into a damaged token.  Compatibility mode preserves
    backslashes on Windows; its surrounding quote characters are removed here
    because ``subprocess.run`` will quote argv for CreateProcess itself.

    The optional ``windows`` argument exists for deterministic cross-platform
    tests.  Runtime callers should leave it unset.
    """

    text = str(command_line or "").strip()
    if not text:
        return []
    use_windows_rules = os.name == "nt" if windows is None else bool(windows)
    parts = shlex.split(text, posix=not use_windows_rules)
    if not use_windows_rules:
        return parts
    return [
        part[1:-1]
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}
        else part
        for part in parts
    ]
