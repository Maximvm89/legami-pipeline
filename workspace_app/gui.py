"""Legami Workspace — PySide6 desktop GUI.

Navigable, color-coded tree of the FTP project (server-only / local-only / both),
with lazy loading for speed: the top level shows instantly and each folder's
contents load only when you expand it, over a single persistent connection.

Run:  python -m workspace_app        (from the toolkit folder, venv active)
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QGroupBox,
)

from animpipe.config import ProjectConfig, SFTPCredentials
from animpipe.sftp import SFTPClient
from . import core

SERVER_BG, SERVER_FG = QColor(250, 238, 218), QColor(133, 79, 11)
LOCAL_BG, LOCAL_FG = QColor(230, 241, 251), QColor(12, 68, 124)
SYNC_BG, SYNC_FG = QColor(225, 245, 238), QColor(8, 80, 65)
NEWER_L_BG = QColor(203, 225, 255)
NEWER_R_BG = QColor(255, 230, 191)
DIFF_BG, DIFF_FG = QColor(252, 235, 235), QColor(163, 45, 45)

ROLE_NODE = Qt.UserRole
ROLE_LOADED = Qt.UserRole + 1


def _fmt_time(ts):
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def node_style(node):
    loc = node.location
    if loc == core.LOC_SERVER_ONLY:
        return ("server only", SERVER_BG, SERVER_FG)
    if loc == core.LOC_LOCAL_ONLY:
        return ("local only", LOCAL_BG, LOCAL_FG)
    st = node.file_status
    if st == core.LOCAL_NEWER:
        return ("both · local newer", NEWER_L_BG, LOCAL_FG)
    if st == core.REMOTE_NEWER:
        return ("both · server newer", NEWER_R_BG, SERVER_FG)
    if st == core.SIZE_DIFFERS:
        return ("both · differs", DIFF_BG, DIFF_FG)
    return ("both", SYNC_BG, SYNC_FG)


def is_download_candidate(f):
    return f.in_remote and not f.is_dir and (
        f.location == core.LOC_SERVER_ONLY or f.file_status == core.REMOTE_NEWER)


def is_upload_candidate(f):
    return f.in_local and not f.is_dir and (
        f.location == core.LOC_LOCAL_ONLY or f.file_status == core.LOCAL_NEWER)


class Job(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, config_path="config.yaml"):
        super().__init__()
        self.setWindowTitle("Legami Workspace")
        self.resize(1040, 680)
        self.config_path = config_path
        self.cfg: ProjectConfig | None = None
        self._conn: SFTPClient | None = None
        self._lock = threading.Lock()
        self._jobs: list[Job] = []
        self._summary = "Ready."
        self._full_tree: core.TreeNode | None = None  # cached full scan for filters

        self._build_menu()
        self._build_ui()
        self._load_config()
        # Auto-load the top level shortly after the window appears.
        QTimer.singleShot(150, self._load_root)

    # ---- connection (persistent, serialized via lock) -----------------------
    def _conn_do(self, fn):
        with self._lock:
            if self._conn is None:
                c = SFTPClient(self._creds())
                c.connect()
                self._conn = c
            try:
                return fn(self._conn)
            except (OSError, EOFError):  # transport dropped -> reconnect once
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
                c = SFTPClient(self._creds())
                c.connect()
                self._conn = c
                return fn(self._conn)

    def closeEvent(self, event):
        if self._conn:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(event)

    # ---- UI -----------------------------------------------------------------
    def _build_menu(self):
        m = self.menuBar().addMenu("File")
        act = QAction("Open config…", self)
        act.triggered.connect(self._pick_config)
        m.addAction(act)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        box = QGroupBox("Project")
        grid = QGridLayout(box)
        self.lbl_project = QLabel("—")
        grid.addWidget(QLabel("Project:"), 0, 0)
        grid.addWidget(self.lbl_project, 0, 1, 1, 3)
        grid.addWidget(QLabel("Local folder:"), 1, 0)
        self.ed_local = QLineEdit()
        grid.addWidget(self.ed_local, 1, 1, 1, 2)
        b_local = QPushButton("Browse…")
        b_local.clicked.connect(self._pick_local)
        grid.addWidget(b_local, 1, 3)
        grid.addWidget(QLabel("FTP password:"), 2, 0)
        self.ed_pass = QLineEdit()
        self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_pass.setPlaceholderText("(from .env if blank)")
        grid.addWidget(self.ed_pass, 2, 1, 1, 2)
        outer.addWidget(box)

        actions = QHBoxLayout()
        self.b_mirror = QPushButton("Create Local Structure")
        self.b_mirror.clicked.connect(self._on_mirror)
        self.b_configure = QPushButton("Configure Blender → this folder")
        self.b_configure.clicked.connect(self._on_configure)
        self.b_refresh = QPushButton("Refresh")
        self.b_refresh.clicked.connect(self._refresh)
        actions.addWidget(self.b_mirror)
        actions.addWidget(self.b_configure)
        actions.addStretch(1)
        actions.addWidget(self.b_refresh)
        outer.addLayout(actions)

        # Filter buttons (multi-select). Toggling any runs a full scan and shows
        # only matching files; unchecking all returns to fast lazy browsing.
        filt = QHBoxLayout()
        filt.addWidget(QLabel("Filter:"))
        self._filter_btns: dict[str, QPushButton] = {}
        for key, text, bg, fg in (("server", "server only", SERVER_BG, SERVER_FG),
                                  ("local", "local only", LOCAL_BG, LOCAL_FG),
                                  ("sync", "both (in sync)", SYNC_BG, SYNC_FG),
                                  ("differs", "differs", DIFF_BG, DIFF_FG)):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setStyleSheet(
                f"QPushButton {{ padding:3px 12px; border-radius:6px; "
                f"border:1px solid {bg.darker(115).name()}; color:{fg.name()}; }} "
                f"QPushButton:checked {{ background:{bg.name()}; font-weight:600; }}")
            b.toggled.connect(self._apply_filter)
            self._filter_btns[key] = b
            filt.addWidget(b)
        filt.addStretch(1)
        outer.addLayout(filt)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Name", "Where", "Local", "Remote", "Modified"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            self.tree.header().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemExpanded.connect(self._on_expand)
        outer.addWidget(self.tree, 1)

        transfer = QHBoxLayout()
        self.b_download = QPushButton("⬇ Download selected")
        self.b_download.clicked.connect(lambda: self._on_transfer("download", True))
        self.b_upload = QPushButton("⬆ Upload selected")
        self.b_upload.clicked.connect(lambda: self._on_transfer("upload", True))
        self.b_download_all = QPushButton("⬇ Download all from server")
        self.b_download_all.clicked.connect(lambda: self._on_transfer("download", False))
        self.b_upload_all = QPushButton("⬆ Upload all local changes")
        self.b_upload_all.clicked.connect(lambda: self._on_transfer("upload", False))
        for b in (self.b_download, self.b_upload, self.b_download_all, self.b_upload_all):
            transfer.addWidget(b)
        outer.addLayout(transfer)

        self.status = self.statusBar()
        self.status.showMessage("Ready.")

    # ---- config / creds -----------------------------------------------------
    def _load_config(self):
        path = self.config_path
        if not os.path.isfile(path):
            self.lbl_project.setText("config.yaml not found — File ▸ Open config…")
            return
        try:
            self.cfg = ProjectConfig.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Config error", str(exc))
            return
        self.lbl_project.setText(f"{self.cfg.name} [{self.cfg.code}]  →  {self.cfg.remote_root}")
        if not self.ed_local.text().strip():
            self.ed_local.setText(self.cfg.resolved_local_root())

    def _creds(self) -> SFTPCredentials:
        creds = SFTPCredentials.from_env(".env")
        pw = self.ed_pass.text().strip()
        if pw:
            creds.password = pw
        return creds

    # ---- job runners --------------------------------------------------------
    def _spawn(self, fn, on_done, busy_msg="Working…"):
        self.status.showMessage(busy_msg)
        job = Job(fn)
        self._jobs.append(job)
        job.done.connect(lambda r, j=job: (self._jobs.remove(j) if j in self._jobs else None, on_done(r)))
        job.failed.connect(lambda m, j=job: (self._jobs.remove(j) if j in self._jobs else None, self._on_error(m)))
        job.start()

    def _busy_buttons(self, on):
        for b in (self.b_mirror, self.b_configure, self.b_refresh, self.b_download,
                  self.b_upload, self.b_download_all, self.b_upload_all):
            b.setEnabled(not on)

    def _run(self, fn, on_done):
        self._busy_buttons(True)
        self._spawn(fn, lambda r: (self._busy_buttons(False), on_done(r)))

    def _on_error(self, msg):
        self._busy_buttons(False)
        self.status.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)

    # ---- pickers ------------------------------------------------------------
    def _pick_config(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select config.yaml", "",
                                           "YAML (*.yaml *.yml)")
        if p:
            self.config_path = p
            self._load_config()
            self._load_root()

    def _pick_local(self):
        p = QFileDialog.getExistingDirectory(self, "Select local project folder")
        if p:
            self.ed_local.setText(p)
            self._load_root()

    # ---- actions ------------------------------------------------------------
    def _on_mirror(self):
        if not self.cfg:
            return
        local = self.ed_local.text().strip()
        remote = self.cfg.remote_root

        def work():
            return self._conn_do(lambda c: core.mirror_structure(c, remote, local))

        def done(created):
            self._busy_buttons(False)
            QMessageBox.information(self, "Structure created",
                                    f"Mirrored {len(created)} folder(s) locally.")
            self._refresh()

        self._busy_buttons(True)
        self._spawn(work, done, busy_msg="Creating local structure…")

    def _on_configure(self):
        if not self.cfg:
            return
        local = self.ed_local.text().strip()
        try:
            core.set_local_root_in_config(self.config_path, local)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Could not configure", str(exc))
            return
        QMessageBox.information(
            self, "Blender configured",
            f"Saved local folder to config.yaml.\nThe launcher and Blender addon "
            f"will now save into:\n{local}")

    # ---- lazy tree ----------------------------------------------------------
    def _make_item(self, node, lazy=True) -> QTreeWidgetItem:
        label, bg, fg = node_style(node)
        cols = [
            node.name, label,
            core.human_size(node.local_size) if node.in_local and not node.is_dir else "",
            core.human_size(node.remote_size) if node.in_remote and not node.is_dir else "",
            _fmt_time(node.local_mtime or node.remote_mtime),
        ]
        item = QTreeWidgetItem(cols)
        for c in range(5):
            item.setBackground(c, QBrush(bg))
            item.setForeground(c, QBrush(fg))
        item.setData(0, ROLE_NODE, node)
        if lazy:
            item.setData(0, ROLE_LOADED, False)
            if node.is_dir:
                item.addChild(QTreeWidgetItem(["Loading…"]))  # placeholder -> arrow
        else:
            item.setData(0, ROLE_LOADED, True)  # filtered tree is fully built
        return item

    def _load_root(self):
        if not self.cfg:
            return
        local = self.ed_local.text().strip()
        remote = self.cfg.remote_root

        def work():
            children = self._conn_do(lambda c: core.merge_children(
                c.listdir(remote), local, ""))
            count, total = core.local_total_all(local)
            return children, count, total

        def done(result):
            self._busy_buttons(False)
            children, count, total = result
            self.tree.clear()
            for node in children:
                self.tree.addTopLevelItem(self._make_item(node))
            self._summary = (
                f"Local: {count} files, {core.human_size(total)} on disk"
                f"   |   expand a folder to compare it with the server")
            self.status.showMessage(self._summary)

        self._busy_buttons(True)
        self._spawn(work, done, busy_msg="Loading project…")

    def _on_expand(self, item: QTreeWidgetItem):
        if item.data(0, ROLE_LOADED):
            return
        node = item.data(0, ROLE_NODE)
        if node is None or not node.is_dir:
            return
        item.setData(0, ROLE_LOADED, True)
        local = self.ed_local.text().strip()
        remote = core.remote_path_for(self.cfg.remote_root, node.rel)

        def work():
            return core.merge_children(
                self._conn_do(lambda c: c.listdir(remote)), local, node.rel)

        def done(children):
            item.takeChildren()  # drop the placeholder
            for child in children:
                item.addChild(self._make_item(child))
            if not children:
                item.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicator)
            self.status.showMessage(self._summary)  # restore disk-usage line

        self._spawn(work, done, busy_msg=f"Loading {node.rel}…")

    # ---- filtering ----------------------------------------------------------
    def _active_filters(self) -> set[str]:
        return {k for k, b in self._filter_btns.items() if b.isChecked()}

    def _refresh(self):
        """Re-read from the server. Re-applies the active filter (full rescan) or
        reloads the lazy top level."""
        self._full_tree = None  # force fresh data
        if self._active_filters():
            self._apply_filter()
        else:
            self._load_root()

    def _apply_filter(self):
        if not self.cfg:
            return
        selected = self._active_filters()
        if not selected:
            self._load_root()  # back to fast browsing
            return
        if self._full_tree is not None:
            self._populate_filtered(self._full_tree, selected)  # instant re-filter
            return
        local = self.ed_local.text().strip()
        remote = self.cfg.remote_root

        def work():
            return self._conn_do(lambda c: core.build_merged_tree(c, remote, local))

        def done(tree):
            self._busy_buttons(False)
            self._full_tree = tree
            self._populate_filtered(tree, self._active_filters())

        self._busy_buttons(True)
        self._spawn(work, done, busy_msg="Scanning server to filter…")

    @staticmethod
    def _matches(node, selected) -> bool:
        if node.is_dir:
            return False
        loc, st = node.location, node.file_status
        return (("server" in selected and loc == core.LOC_SERVER_ONLY)
                or ("local" in selected and loc == core.LOC_LOCAL_ONLY)
                or ("sync" in selected and loc == core.LOC_BOTH and st == core.IN_SYNC)
                or ("differs" in selected and loc == core.LOC_BOTH
                    and st not in (None, core.IN_SYNC)))

    def _populate_filtered(self, root, selected):
        self.tree.clear()

        def build(node):
            items = []
            for name in sorted(node.children,
                               key=lambda n: (not node.children[n].is_dir, n.lower())):
                child = node.children[name]
                if child.is_dir:
                    sub = build(child)
                    if sub:  # only show folders that contain matches
                        it = self._make_item(child, lazy=False)
                        it.addChildren(sub)
                        items.append(it)
                elif self._matches(child, selected):
                    items.append(self._make_item(child, lazy=False))
            return items

        self.tree.addTopLevelItems(build(root))
        self.tree.expandAll()
        count = sum(1 for f in core.iter_files(root) if self._matches(f, selected))
        labels = ", ".join(self._filter_btns[k].text() for k in
                           ("server", "local", "sync", "differs") if k in selected)
        self.status.showMessage(f"Filter [{labels}]: {count} file(s) match")

    # ---- transfers ----------------------------------------------------------
    def _selected_nodes(self):
        out = []
        for item in self.tree.selectedItems():
            n = item.data(0, ROLE_NODE)
            if n:
                out.append(n)
        return out

    def _on_transfer(self, direction: str, selected: bool):
        if not self.cfg:
            return
        local_root = self.ed_local.text().strip()
        remote_root = self.cfg.remote_root
        pred = is_download_candidate if direction == "download" else is_upload_candidate
        roots = self._selected_nodes() if selected else [None]  # None = whole project
        if selected and not roots:
            QMessageBox.information(self, "Nothing selected", "Select files or folders first.")
            return
        verb = "Upload" if direction == "upload" else "Download"

        def work():
            # Build a (sub)tree for each root by a scoped recursive walk, collect candidates.
            chosen: dict[str, core.TreeNode] = {}
            for r in roots:
                rel = r.rel if r else ""
                rroot = core.remote_path_for(remote_root, rel) if rel else remote_root
                lroot = core.local_path_for(local_root, rel) if rel else local_root
                if r and not r.is_dir:  # a single selected file
                    if pred(r):
                        chosen[r.rel] = r
                    continue
                tree = self._conn_do(lambda c, rr=rroot, lr=lroot:
                                     core.build_merged_tree(c, rr, lr))
                for f in core.iter_files(tree):
                    if pred(f):
                        # f.rel is relative to the sub-root; re-anchor under rel
                        full_rel = f"{rel}/{f.rel}" if rel else f.rel
                        f.rel = full_rel
                        chosen[full_rel] = f
            files = list(chosen.values())
            if not files:
                return 0
            for f in files:
                rp = core.remote_path_for(remote_root, f.rel)
                lp = core.local_path_for(local_root, f.rel)
                self._conn_do(lambda c, a=lp, b=rp:
                              c.upload(a, b) if direction == "upload" else c.download(b, a))
            return len(files)

        def done(n):
            self._busy_buttons(False)
            if n == 0:
                self.status.showMessage("Nothing to transfer (already in sync).")
            else:
                self.status.showMessage(f"{verb}ed {n} file(s). Refreshing…")
                self._refresh()

        self._busy_buttons(True)
        self._spawn(work, done, busy_msg=f"{verb}ing…")


def main():
    app = QApplication(sys.argv)
    config = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    win = MainWindow(config)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
