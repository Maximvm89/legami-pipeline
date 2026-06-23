# Legami Workspace — desktop app

A cross-platform (Windows / macOS / Linux) GUI for artists to manage their local
copy of the project and sync work/publish files with the FTP.

## What it does

1. **Create Local Structure** — does a *shallow copy* of the project from the FTP:
   it recreates the full folder tree locally (folders only, no files) at a path
   you choose.
2. **Configure Blender → this folder** — writes that local path into `config.yaml`
   so the launcher and the Blender addon save your files into the right structure.
3. **Refresh / Diff** — shows the whole project as a navigable folder **tree**
   (expand/collapse), merging the FTP and your local copy. Every folder and file
   is color-coded by where it lives:

   | Color | Where | Action |
   |---|---|---|
   | Amber | Server only | download |
   | Blue | Local only | upload |
   | Teal/green | Both, in sync | none |
   | Blue (stronger) | Both, local newer | upload |
   | Amber (stronger) | Both, server newer | download |
   | Red | Both, size differs | review (possible conflict) |

   Comparison of files present on both sides is by size + modified time.

4. **Upload / Download** — selected files, or "all local-newer" / "all
   remote-newer" in one click. Transfers preserve modified-times so the diff
   stays clean.
5. **Live totals** — the status bar always shows how many files you have locally
   and their exact total size, plus counts per status.

Comparison is by **size + modified time** (fast, no full downloads needed).

## Install (one-time)

The app needs PySide6 in addition to the base tools:

```bash
cd ~/legami
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-gui.txt
```

You also need `config.yaml` (project + remote_root) and `.env` (your FTP login)
in the toolkit folder, same as the other tools.

## Run

Double-click the wrapper for your OS in `launcher/`:

- `Legami-Workspace-mac.command`
- `Legami-Workspace-windows.bat`
- `Legami-Workspace-linux.sh`

…or from a terminal: `python3 -m workspace_app`

## Typical first use

1. Open the app. It reads `config.yaml` and shows the project + remote root.
2. Pick a **Local folder** (or accept the default `~/Legami/<CODE>`).
3. Click **Create Local Structure** → the empty folder tree appears locally.
4. Click **Configure Blender → this folder** → the pipeline now saves here.
5. Work in Blender, saving scenes into the matching `work/` folders.
6. Click **Refresh / Diff**, then **Upload all local-newer** to publish your
   changes to the FTP. Pull teammates' updates with **Download all remote-newer**.

## Performance (lazy loading)

The tree loads **lazily**: opening the app shows only the top level instantly, and
each folder's contents are fetched from the server only when you expand it, over
a single persistent connection. This keeps browsing fast even on large projects.

- The status bar shows your local file count + total size immediately (computed
  from the local disk, no network).
- Expanding a folder compares just that folder against the server.
- The bulk buttons ("Download all from server" / "Upload all local changes")
  and the filter buttons do a full recursive scan on demand. That scan lists
  folders **in parallel** over several SFTP channels (~8–15× faster than serial),
  and the result is cached so toggling filters afterwards is instant.

`config.yaml` is auto-loaded from the toolkit folder. To point at a different
project, use **File ▸ Open config…**

## Notes

- Password: taken from `.env`. On a shared machine, leave `.env` blank and type it
  into the password field each session.
- Diff currently walks the whole remote tree and filters to `work/`+`publish/`.
  Fine for normal projects; if the tree grows huge this is the place to optimize.
- "Size differs" means two people edited the same file to different sizes — the
  app flags it rather than guessing; resolve by choosing which to keep.
