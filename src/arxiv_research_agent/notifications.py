"""Local user notifications with no shell interpolation."""

import subprocess
import sys
from typing import Callable


def notify_macos(
    title: str,
    message: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    if sys.platform != "darwin":
        return False
    script = "display notification %s with title %s" % (
        _apple_string(message[:240]),
        _apple_string(title[:80]),
    )
    try:
        result = runner(
            ["/usr/bin/osascript", "-e", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _apple_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped
