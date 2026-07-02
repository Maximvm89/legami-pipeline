"""Upload attribution ledgers stored on the server.

Each user writes only their own file (02_pipeline/.uploads/<user>.json), so
concurrent uploads from different artists never conflict. A ledger maps a
path (relative to the project's remote_root) to the upload time.

Lives in flumen (the low-level layer) so both the CLI and the workspace app
share one implementation. Needs an sftp object with listdir / read_text /
write_text (flumen.sftp.SFTPClient provides these).
"""

from __future__ import annotations

import json
import time

UPLOADS_DIR_REL = "02_pipeline/.uploads"


def uploads_dir(remote_root: str) -> str:
    return remote_root.rstrip("/") + "/" + UPLOADS_DIR_REL


def load_ledgers(sftp, remote_root: str) -> dict[str, tuple[str, float]]:
    """Merge all per-user ledgers into rel -> (user, time). Latest time wins."""
    out: dict[str, tuple[str, float]] = {}
    d = uploads_dir(remote_root)
    for e in sftp.listdir(d):
        if e["is_dir"] or not e["name"].endswith(".json"):
            continue
        user = e["name"][:-5]
        txt = sftp.read_text(d + "/" + e["name"])
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except ValueError:
            continue
        for rel, ts in data.items():
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                continue
            if rel not in out or ts > out[rel][1]:
                out[rel] = (user, ts)
    return out


def record_uploads(sftp, remote_root: str, username: str,
                   rels: list[str]) -> None:
    """Append/refresh the current user's ledger with just-uploaded paths."""
    if not rels or not username:
        return
    path = uploads_dir(remote_root) + "/" + username + ".json"
    existing: dict = {}
    txt = sftp.read_text(path)
    if txt:
        try:
            existing = json.loads(txt)
        except ValueError:
            existing = {}
    now = time.time()
    for rel in rels:
        existing[rel] = now
    sftp.write_text(path, json.dumps(existing))
