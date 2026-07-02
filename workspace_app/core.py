"""Workspace logic — no GUI, no Qt. Unit-testable.

Responsibilities:
  * mirror_structure: shallow copy (folders only) of the remote project locally
  * scan_local:       list local files under work/ and publish/ with sizes
  * diff:             compare local vs remote by size + modified time
  * set_local_root_in_config: point the rest of the pipeline at the local root
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

# Where per-user upload ledgers live on the server (under remote_root).
UPLOADS_DIR_REL = "02_pipeline/.uploads"

AREA_NAMES = ("work", "publish")
# junk files we never show or transfer
IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def _ignored(name: str) -> bool:
    return name in IGNORE_NAMES or name.startswith(".")
MTIME_TOLERANCE = 2.0  # seconds; filesystems/servers round mtimes differently

# Diff statuses
IN_SYNC = "in_sync"
LOCAL_ONLY = "local_only"      # exists locally, not on FTP  -> upload candidate
REMOTE_ONLY = "remote_only"    # exists on FTP, not locally  -> download candidate
LOCAL_NEWER = "local_newer"    # -> upload candidate
REMOTE_NEWER = "remote_newer"  # -> download candidate
SIZE_DIFFERS = "size_differs"  # same path, different size   -> needs attention


@dataclass
class DiffRow:
    rel: str
    status: str
    local_size: int | None
    remote_size: int | None
    local_mtime: float | None
    remote_mtime: float | None


def in_tracked_area(rel: str, area_names=AREA_NAMES) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(p in area_names for p in parts)


# --- shallow copy of the structure ------------------------------------------
def mirror_structure(sftp, remote_root: str, local_root: str) -> list[str]:
    """Create the remote folder tree locally (directories only). Returns the list
    of directories created (skips ones that already exist)."""
    created: list[str] = []
    os.makedirs(local_root, exist_ok=True)
    for entry in sftp.walk_remote(remote_root):
        if not entry["is_dir"]:
            continue
        local_dir = os.path.join(local_root, *entry["rel"].split("/"))
        if not os.path.isdir(local_dir):
            os.makedirs(local_dir, exist_ok=True)
            created.append(local_dir)
    return created


# --- local scan -------------------------------------------------------------
def scan_local(local_root: str, area_names=AREA_NAMES) -> dict[str, tuple[int, float]]:
    """Map rel-path -> (size, mtime) for files under tracked areas."""
    out: dict[str, tuple[int, float]] = {}
    for dirpath, _dirs, files in os.walk(local_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, local_root).replace("\\", "/")
            if not in_tracked_area(rel, area_names):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            out[rel] = (st.st_size, st.st_mtime)
    return out


def local_total_size(local_files: dict[str, tuple[int, float]]) -> int:
    return sum(sz for sz, _ in local_files.values())


# --- diff -------------------------------------------------------------------
def _status(lsz, lmt, rsz, rmt) -> str:
    if lsz != rsz:
        return SIZE_DIFFERS
    if lmt is not None and rmt is not None:
        if lmt > rmt + MTIME_TOLERANCE:
            return LOCAL_NEWER
        if rmt > lmt + MTIME_TOLERANCE:
            return REMOTE_NEWER
    return IN_SYNC


def diff(sftp, remote_root: str, local_root: str,
         area_names=AREA_NAMES) -> list[DiffRow]:
    """Compare tracked-area files between local and remote."""
    remote_files = {
        e["rel"]: e for e in sftp.walk_remote(remote_root)
        if not e["is_dir"] and in_tracked_area(e["rel"], area_names)
    }
    local_files = scan_local(local_root, area_names)

    rows: list[DiffRow] = []
    for rel in sorted(set(remote_files) | set(local_files)):
        loc = local_files.get(rel)
        rem = remote_files.get(rel)
        if loc and rem:
            status = _status(loc[0], loc[1], rem["size"], rem["mtime"])
            rows.append(DiffRow(rel, status, loc[0], rem["size"], loc[1], rem["mtime"]))
        elif loc and not rem:
            rows.append(DiffRow(rel, LOCAL_ONLY, loc[0], None, loc[1], None))
        else:
            rows.append(DiffRow(rel, REMOTE_ONLY, None, rem["size"], None, rem["mtime"]))
    return rows


def summarize(rows: list[DiffRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


# --- helpers for transfers --------------------------------------------------
def remote_path_for(remote_root: str, rel: str) -> str:
    return remote_root.rstrip("/") + "/" + rel


def local_path_for(local_root: str, rel: str) -> str:
    return os.path.join(local_root, *rel.split("/"))


# --- wire the rest of the pipeline to the chosen local root -----------------
def set_local_root_in_config(config_path: str, value: str) -> None:
    """Set project.local_root in config.yaml, preserving comments. This is how
    'Configure Blender' makes the launcher + addon save into this structure."""
    with open(config_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    value_line_re = re.compile(r"^(\s*)local_root:\s*.*$")
    remote_re = re.compile(r"^(\s*)remote_root:\s*.*$")

    # 1. replace an existing active local_root line
    for i, line in enumerate(lines):
        if value_line_re.match(line) and not line.lstrip().startswith("#"):
            indent = value_line_re.match(line).group(1)
            lines[i] = f'{indent}local_root: "{value}"'
            break
    else:
        # 2. otherwise insert right after remote_root
        for i, line in enumerate(lines):
            if remote_re.match(line):
                indent = remote_re.match(line).group(1)
                lines.insert(i + 1, f'{indent}local_root: "{value}"')
                break
        else:
            raise ValueError("could not find project.remote_root in config to anchor local_root")

    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ===========================================================================
# Merged remote+local TREE model (for the navigable tree view)
# ===========================================================================
from dataclasses import field

# location of a node
LOC_BOTH = "both"
LOC_SERVER_ONLY = "server_only"   # exists on FTP, not locally
LOC_LOCAL_ONLY = "local_only_loc"  # exists locally, not on FTP


@dataclass
class TreeNode:
    name: str
    rel: str
    is_dir: bool
    in_remote: bool = False
    in_local: bool = False
    local_size: int | None = None
    remote_size: int | None = None
    local_mtime: float | None = None
    remote_mtime: float | None = None
    owner: str = ""              # server file owner (from SFTP listing), if any
    children: dict = field(default_factory=dict)

    # --- derived ---
    @property
    def location(self) -> str:
        if self.in_remote and self.in_local:
            return LOC_BOTH
        if self.in_remote:
            return LOC_SERVER_ONLY
        if self.in_local:
            return LOC_LOCAL_ONLY
        # intermediate dir: infer from children
        locs = {c.location for c in self.children.values()}
        if LOC_BOTH in locs or (LOC_SERVER_ONLY in locs and LOC_LOCAL_ONLY in locs):
            return LOC_BOTH
        if LOC_SERVER_ONLY in locs:
            return LOC_SERVER_ONLY
        return LOC_LOCAL_ONLY

    @property
    def file_status(self) -> str | None:
        """For files present on both sides: in_sync / *_newer / size_differs."""
        if self.is_dir or self.location != LOC_BOTH:
            return None
        return _status(self.local_size, self.local_mtime,
                       self.remote_size, self.remote_mtime)


def walk_local_full(local_root: str) -> dict[str, tuple[bool, int, float]]:
    """rel -> (is_dir, size, mtime) for every dir and file under local_root."""
    out: dict[str, tuple[bool, int, float]] = {}
    for dirpath, dirs, files in os.walk(local_root):
        dirs[:] = [d for d in dirs if not _ignored(d)]  # prune hidden dirs in-place
        for d in dirs:
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, local_root).replace("\\", "/")
            out[rel] = (True, 0, 0.0)
        for f in files:
            if _ignored(f):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, local_root).replace("\\", "/")
            try:
                st = os.stat(full)
            except OSError:
                continue
            out[rel] = (False, st.st_size, st.st_mtime)
    return out


def build_merged_tree(sftp, remote_root: str, local_root: str) -> TreeNode:
    """Merge the full remote tree and the full local tree into one node tree."""
    root = TreeNode(name="", rel="", is_dir=True)

    def ensure(rel: str, is_dir: bool) -> TreeNode:
        node = root
        cur = ""
        parts = rel.split("/")
        for i, part in enumerate(parts):
            cur = part if not cur else f"{cur}/{part}"
            last = i == len(parts) - 1
            if part not in node.children:
                node.children[part] = TreeNode(name=part, rel=cur,
                                               is_dir=(is_dir if last else True))
            node = node.children[part]
            if last:
                node.is_dir = is_dir
        return node

    for e in sftp.walk_remote(remote_root):
        if any(_ignored(part) for part in e["rel"].split("/")):
            continue  # skip .uploads ledgers, .DS_Store, etc.
        n = ensure(e["rel"], e["is_dir"])
        n.in_remote = True
        n.owner = e.get("owner", "")
        if not e["is_dir"]:
            n.remote_size = int(e["size"])
            n.remote_mtime = float(e["mtime"])

    for rel, (is_dir, size, mtime) in walk_local_full(local_root).items():
        n = ensure(rel, is_dir)
        n.in_local = True
        if not is_dir:
            n.local_size = size
            n.local_mtime = mtime

    return root


def merge_children(remote_entries: list[dict], local_root: str,
                   parent_rel: str = "") -> list[TreeNode]:
    """Merge ONE directory level: remote listing + local scandir -> child nodes.
    Used for lazy/on-demand tree expansion (fast — one dir at a time)."""
    if parent_rel:
        local_dir = os.path.join(local_root, *parent_rel.split("/"))
    else:
        local_dir = local_root

    local: dict[str, tuple[bool, int, float]] = {}
    if os.path.isdir(local_dir):
        try:
            for de in os.scandir(local_dir):
                if _ignored(de.name):
                    continue
                try:
                    is_dir = de.is_dir()
                    st = de.stat()
                    local[de.name] = (is_dir, st.st_size, st.st_mtime)
                except OSError:
                    continue
        except OSError:
            pass

    rmap = {e["name"]: e for e in remote_entries if not _ignored(e["name"])}
    nodes: list[TreeNode] = []
    for name in set(rmap) | set(local):
        rel = f"{parent_rel}/{name}" if parent_rel else name
        r = rmap.get(name)
        l = local.get(name)
        is_dir = r["is_dir"] if r else l[0]
        node = TreeNode(name=name, rel=rel, is_dir=is_dir)
        if r:
            node.in_remote = True
            node.owner = r.get("owner", "")
            if not r["is_dir"]:
                node.remote_size = r["size"]
                node.remote_mtime = r["mtime"]
        if l:
            node.in_local = True
            if not l[0]:
                node.local_size = l[1]
                node.local_mtime = l[2]
        nodes.append(node)
    nodes.sort(key=lambda n: (not n.is_dir, n.name.lower()))
    return nodes


def local_total_all(local_root: str) -> tuple[int, int]:
    """(file_count, total_bytes) for every file under local_root. Fast (local FS)."""
    count = 0
    total = 0
    if not os.path.isdir(local_root):
        return (0, 0)
    for _dp, _dirs, files in os.walk(local_root):
        _dirs[:] = [d for d in _dirs if not _ignored(d)]
        for f in files:
            if _ignored(f):
                continue
            try:
                total += os.path.getsize(os.path.join(_dp, f))
                count += 1
            except OSError:
                continue
    return (count, total)


def iter_files(node: TreeNode):
    """Yield all file nodes under (and including) node."""
    if not node.is_dir:
        yield node
        return
    for child in node.children.values():
        yield from iter_files(child)


def summarize_tree(root: TreeNode) -> dict:
    files = [f for f in iter_files(root)]
    local_files = [f for f in files if f.in_local]
    out = {
        "local_files": len(local_files),
        "local_bytes": sum(f.local_size or 0 for f in local_files),
        "server_only": sum(1 for f in files if f.location == LOC_SERVER_ONLY),
        "local_only": sum(1 for f in files if f.location == LOC_LOCAL_ONLY),
        "both": sum(1 for f in files if f.location == LOC_BOTH),
        "differs": sum(1 for f in files
                       if f.location == LOC_BOTH and f.file_status != IN_SYNC),
    }
    return out


# ===========================================================================
# Upload attribution — ledgers live in flumen.ledger (shared with the CLI)
# ===========================================================================
from flumen.ledger import load_ledgers, record_uploads  # noqa: E402,F401


def uploader_for(node: TreeNode, ledger: dict[str, tuple[str, float]]) -> str:
    """Resolve who pushed a file: ledger first, then server file owner."""
    if node.is_dir:
        return ""
    entry = ledger.get(node.rel)
    if entry:
        return entry[0]
    return node.owner or ""


def human_size(n: int | None) -> str:
    if n is None:
        return "—"
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"
