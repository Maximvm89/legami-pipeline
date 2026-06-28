"""Project user roster: who is allowed on the project, for task assignment.

SFTP can't enumerate the server's accounts, so the roster lives with the project
under 02_pipeline/, in two parts that MERGE into one effective list:

  * users.json          — the curated roster an admin maintains: display name,
                          role (artist/supervisor), active flag. Low-frequency,
                          single-writer (the admin), so one shared file is fine.
  * .users/<name>.json  — per-user self-registration written on sign-in (username
                          + last_seen). Conflict-free (each user writes only their
                          own file), exactly like the upload ledger.

The effective roster = curated ∪ self-registered; curated entries win for
display/role/active. A self-registered user not yet curated defaults to an active
artist. `username` is the SFTP login — the identity used everywhere else
(uploads, attribution, task assignees, the "My tasks" scope).

Pure helpers here are unit-testable; the GUI/CLI drive load/save/register.
"""

from __future__ import annotations

import json
import time

USERS_FILE_REL = "02_pipeline/users.json"
SELF_DIR_REL = "02_pipeline/.users"

ARTIST = "artist"
SUPERVISOR = "supervisor"
ROLES = [ARTIST, SUPERVISOR]
DEFAULT_ROLE = ARTIST


def users_file(remote_root: str) -> str:
    return remote_root.rstrip("/") + "/" + USERS_FILE_REL


def self_dir(remote_root: str) -> str:
    return remote_root.rstrip("/") + "/" + SELF_DIR_REL


def new_user(username: str, display: str = "", role: str = DEFAULT_ROLE,
             active: bool = True, last_seen: float | None = None) -> dict:
    """A roster entry. `display` defaults to the username; role is validated."""
    return {
        "username": username,
        "display": (display or "").strip() or username,
        "role": role if role in ROLES else DEFAULT_ROLE,
        "active": bool(active),
        "last_seen": last_seen,
    }


def merge_roster(curated: list[dict], self_seen: dict[str, float]) -> list[dict]:
    """Merge the curated roster with self-registered users into one effective list.

    curated:   list of roster entries (authoritative for display/role/active).
    self_seen: {username: last_seen} from the per-user files.
    A self-registered user with no curated entry becomes an active artist. A
    curated user keeps their fields; last_seen takes the newest of the two.
    Sorted by display name (case-insensitive)."""
    by_name: dict[str, dict] = {}
    for u in curated or []:
        name = u.get("username")
        if not name:
            continue
        by_name[name] = new_user(
            name, u.get("display", ""), u.get("role", DEFAULT_ROLE),
            u.get("active", True), u.get("last_seen"))
    for name, ts in (self_seen or {}).items():
        if name in by_name:
            cur = by_name[name].get("last_seen")
            if ts and (cur is None or ts > cur):
                by_name[name]["last_seen"] = ts
        else:
            by_name[name] = new_user(name, last_seen=ts)
    return sorted(by_name.values(), key=lambda u: u["display"].lower())


# --- I/O --------------------------------------------------------------------

def _read_curated(sftp, remote_root: str) -> list[dict]:
    txt = sftp.read_text(users_file(remote_root))
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except ValueError:
        return []
    return data.get("users") or []


def _read_self_seen(sftp, remote_root: str) -> dict[str, float]:
    out: dict[str, float] = {}
    d = self_dir(remote_root)
    try:
        entries = sftp.listdir(d)
    except (IOError, OSError):
        return out
    for e in entries:
        if e["is_dir"] or not e["name"].endswith(".json"):
            continue
        name = e["name"][:-5]
        txt = sftp.read_text(d + "/" + e["name"])
        if not txt:
            out.setdefault(name, 0.0)
            continue
        try:
            out[name] = float(json.loads(txt).get("last_seen") or 0.0)
        except (ValueError, TypeError):
            out.setdefault(name, 0.0)
    return out


def load_roster(sftp, remote_root: str) -> list[dict]:
    """The effective roster: curated users.json merged with self-registrations."""
    return merge_roster(_read_curated(sftp, remote_root),
                        _read_self_seen(sftp, remote_root))


def save_roster(sftp, remote_root: str, users: list[dict]) -> None:
    """Write the curated roster (users.json). Normalizes each entry."""
    clean = [new_user(u["username"], u.get("display", ""), u.get("role", DEFAULT_ROLE),
                       u.get("active", True), u.get("last_seen"))
             for u in users if u.get("username")]
    sftp.write_text(users_file(remote_root),
                    json.dumps({"users": clean}, indent=2))


def register_self(sftp, remote_root: str, username: str,
                  when: float | None = None) -> None:
    """Record this user's presence (per-user file, conflict-free). Called on a
    successful sign-in so the roster tracks everyone who actually has access."""
    if not username:
        return
    path = self_dir(remote_root) + "/" + username + ".json"
    sftp.write_text(path, json.dumps(
        {"username": username, "last_seen": when if when is not None else time.time()}))


def discover(sftp, remote_root: str, extra_usernames: list[str] | None = None,
             promote_supervisor: str | None = None) -> list[dict]:
    """Seed/refresh the curated roster from everyone observed: self-registrations,
    the upload ledger, and any `extra_usernames` (e.g. existing task assignees).
    Preserves existing curated entries. If the roster is being created for the
    first time, `promote_supervisor` (the running user) is made a supervisor so
    there is always an admin. Returns the saved roster."""
    from . import ledger
    curated = {u["username"]: u for u in _read_curated(sftp, remote_root)
               if u.get("username")}
    first_time = not curated

    seen = set(_read_self_seen(sftp, remote_root))
    try:
        seen |= {user for (user, _ts) in ledger.load_ledgers(sftp, remote_root).values()}
    except (IOError, OSError):
        pass
    seen |= {u for u in (extra_usernames or []) if u}

    for name in seen:
        if name not in curated:
            curated[name] = new_user(name)
    if first_time and promote_supervisor and promote_supervisor in curated:
        curated[promote_supervisor]["role"] = SUPERVISOR

    out = list(curated.values())
    save_roster(sftp, remote_root, out)
    return merge_roster(out, _read_self_seen(sftp, remote_root))


# --- pure queries -----------------------------------------------------------

def has_supervisor(roster: list[dict]) -> bool:
    """True if at least one active supervisor exists — used to decide whether the
    roster is still un-bootstrapped (anyone may run Discover) or locked down."""
    return any(u.get("role") == SUPERVISOR and u.get("active")
               for u in roster or [])


def is_supervisor(roster: list[dict], username: str) -> bool:
    for u in roster or []:
        if u.get("username") == username:
            return u.get("role") == SUPERVISOR
    return False


def active_users(roster: list[dict]) -> list[dict]:
    return [u for u in roster or [] if u.get("active")]


def display_name(roster: list[dict], username: str) -> str:
    for u in roster or []:
        if u.get("username") == username:
            return u.get("display") or username
    return username
