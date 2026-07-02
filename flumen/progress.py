"""Tiny progress protocol shared between the publish toolkit and the Blender add-on.

The toolkit (cmd_publish) prints `FLUMEN_PROGRESS <pct> <eta> <message>` lines to
stdout as it uploads; the add-on's modal operator reads them and drives a progress
bar + status text. Kept text-based and dependency-free so it survives the subprocess
boundary. Pure + unit-testable.
"""

from __future__ import annotations

PREFIX = "FLUMEN_PROGRESS"


def percent(done: float, total: float) -> int:
    """Integer 0..100. An empty/zero total reads as complete."""
    if total <= 0:
        return 100
    return max(0, min(100, int(done * 100 / total)))


def eta_seconds(done: float, total: float, elapsed: float) -> float | None:
    """Estimated seconds remaining from the average rate so far, or None until
    there's enough signal (some bytes + some time)."""
    if done <= 0 or elapsed <= 0 or total <= 0:
        return None
    rate = done / elapsed
    if rate <= 0:
        return None
    return max(0.0, (total - done) / rate)


def format_line(done: float, total: float, elapsed: float, message: str = "") -> str:
    """Build a `FLUMEN_PROGRESS <pct> <eta> <message>` line (eta blank if unknown)."""
    eta = eta_seconds(done, total, elapsed)
    eta_s = "" if eta is None else f"{eta:.0f}"
    return f"{PREFIX} {percent(done, total)} {eta_s} {message}".rstrip()


def parse_line(line: str):
    """Parse a progress line -> (pct:int, eta:float|None, message:str), or None if
    the line isn't a progress line."""
    if not line or not line.startswith(PREFIX):
        return None
    rest = line[len(PREFIX):].strip().split(" ", 2)
    try:
        pct = int(rest[0])
    except (IndexError, ValueError):
        return None
    eta = None
    if len(rest) > 1 and rest[1]:
        try:
            eta = float(rest[1])
        except ValueError:
            eta = None
    msg = rest[2] if len(rest) > 2 else ""
    return pct, eta, msg


def human_eta(eta: float | None) -> str:
    """'~8s left' / '~2m left' / '' — for a status line."""
    if eta is None:
        return ""
    if eta < 90:
        return f"~{int(eta)}s left"
    return f"~{int(round(eta / 60))}m left"
