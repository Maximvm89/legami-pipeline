"""Project user roster: merge, I/O, self-registration, discover, queries."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flumen import users as U
from test_tasks import FakeSrv

REMOTE = "/shared/Flumen"


def test_new_user_defaults_and_role_validation():
    u = U.new_user("leonardo.milossi")
    assert u["display"] == "leonardo.milossi"        # display defaults to username
    assert u["role"] == U.ARTIST and u["active"] is True
    bad = U.new_user("x", role="wizard")
    assert bad["role"] == U.ARTIST                    # invalid role -> default


def test_merge_prefers_curated_and_adds_self_registered():
    curated = [U.new_user("marco.parisi2", "Marco Parisi", U.SUPERVISOR)]
    self_seen = {"marco.parisi2": 200.0, "leonardo.milossi": 100.0}
    roster = U.merge_roster(curated, self_seen)
    names = [u["username"] for u in roster]
    assert names == ["leonardo.milossi", "marco.parisi2"]   # sorted by display
    marco = next(u for u in roster if u["username"] == "marco.parisi2")
    leo = next(u for u in roster if u["username"] == "leonardo.milossi")
    assert marco["role"] == U.SUPERVISOR and marco["display"] == "Marco Parisi"
    assert marco["last_seen"] == 200.0
    # self-registered, not curated -> active artist
    assert leo["role"] == U.ARTIST and leo["active"] is True


def test_merge_keeps_newest_last_seen():
    curated = [U.new_user("a", last_seen=50.0)]
    roster = U.merge_roster(curated, {"a": 80.0})
    assert roster[0]["last_seen"] == 80.0
    roster2 = U.merge_roster([U.new_user("a", last_seen=90.0)], {"a": 80.0})
    assert roster2[0]["last_seen"] == 90.0


def test_register_self_then_load_roster():
    srv = FakeSrv()
    U.register_self(srv, REMOTE, "leonardo.milossi", when=123.0)
    roster = U.load_roster(srv, REMOTE)
    assert [u["username"] for u in roster] == ["leonardo.milossi"]
    assert roster[0]["last_seen"] == 123.0 and roster[0]["role"] == U.ARTIST


def test_save_and_load_curated_roundtrip():
    srv = FakeSrv()
    U.save_roster(srv, REMOTE, [
        U.new_user("marco.parisi2", "Marco Parisi", U.SUPERVISOR),
        {"username": "leonardo.milossi"},   # minimal -> normalized
    ])
    roster = U.load_roster(srv, REMOTE)
    assert U.is_supervisor(roster, "marco.parisi2")
    assert not U.is_supervisor(roster, "leonardo.milossi")
    assert U.display_name(roster, "marco.parisi2") == "Marco Parisi"
    assert U.display_name(roster, "leonardo.milossi") == "leonardo.milossi"


def test_discover_seeds_and_promotes_first_supervisor():
    srv = FakeSrv()
    # Two users have self-registered; nobody curated yet.
    U.register_self(srv, REMOTE, "marco.parisi2", when=10.0)
    U.register_self(srv, REMOTE, "leonardo.milossi", when=20.0)
    roster = U.discover(srv, REMOTE, extra_usernames=["external.artist"],
                        promote_supervisor="marco.parisi2")
    names = {u["username"] for u in roster}
    assert names == {"marco.parisi2", "leonardo.milossi", "external.artist"}
    assert U.is_supervisor(roster, "marco.parisi2")          # first admin
    assert not U.is_supervisor(roster, "leonardo.milossi")


def test_discover_does_not_repromote_or_clobber_existing():
    srv = FakeSrv()
    U.save_roster(srv, REMOTE, [
        U.new_user("marco.parisi2", "Marco", U.SUPERVISOR),
        U.new_user("leonardo.milossi", "Leo", U.ARTIST, active=False),
    ])
    # roster already exists -> running user is NOT auto-promoted, fields preserved
    roster = U.discover(srv, REMOTE, promote_supervisor="leonardo.milossi")
    leo = next(u for u in roster if u["username"] == "leonardo.milossi")
    assert leo["role"] == U.ARTIST and leo["active"] is False and leo["display"] == "Leo"
    assert U.is_supervisor(roster, "marco.parisi2")


def test_has_supervisor_gates_bootstrap():
    assert not U.has_supervisor([])                          # fresh -> anyone may bootstrap
    assert not U.has_supervisor([U.new_user("a")])          # only artists
    assert not U.has_supervisor([U.new_user("a", role=U.SUPERVISOR, active=False)])
    assert U.has_supervisor([U.new_user("a", role=U.SUPERVISOR)])


def test_active_users_filters_inactive():
    roster = [U.new_user("a", active=True), U.new_user("b", active=False)]
    assert [u["username"] for u in U.active_users(roster)] == ["a"]
