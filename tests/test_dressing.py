"""Set-dressing pure model: naming round-trips, manifest shape, matrix rows."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flumen import dressing as D


def test_normalize_dressing_name():
    assert D.normalize_dressing_name("Night Market!") == "night_market"
    assert D.normalize_dressing_name("  ") == "default"
    assert D.normalize_dressing_name("") == "default"
    assert D.normalize_dressing_name("a--b__c") == "a_b_c"


def test_filename_round_trip_with_underscores():
    # Underscores in both asset and dressing names stay unambiguous because
    # parsing is anchored on the asset's own name.
    fn = D.dressing_filename("market_square", "night market", 3)
    assert fn == "market_square_dressing_night_market_v003.blend"
    assert D.parse_dressing_filename(fn, "market_square") == ("night_market", 3)
    assert D.parse_dressing_filename(fn, "other_asset") is None
    assert D.parse_dressing_filename("market_square_model_v001.blend",
                                     "market_square") is None


def test_manifest_name_for():
    assert D.manifest_name_for("x_dressing_a_v001.blend") == \
        "x_dressing_a_v001.manifest.json"


def test_matrix_to_rows_rounds():
    mat = [[1, 0, 0, 0.12345678], [0, 1, 0, 2], [0, 0, 1, 3], [0, 0, 0, 1]]
    rows = D.matrix_to_rows(mat)
    assert rows[0][3] == 0.123457            # rounded to 6 decimals
    assert rows[3] == [0.0, 0.0, 0.0, 1.0]


def test_build_dressing_manifest_shape():
    env = {"asset": "environments/market_square", "source_step": "model",
           "blend_rel": "03_assets/environments/market_square/model/publish/"
                        "market_square_model_v004.blend"}
    props = [{"id": "lantern_1", "asset": "props/lantern", "source_step": "model",
              "blend_rel": "03_assets/props/lantern/model/publish/"
                           "lantern_model_v002.blend",
              "collection": "lantern", "object": "prop_root__lantern_1",
              "matrix_world": [[1, 0, 0, 0], [0, 1, 0, 0],
                               [0, 0, 1, 0], [0, 0, 0, 1]]}]
    m = D.build_dressing_manifest("Night Market", 3, env, props,
                                  workfile_rel="x/publish/f.blend")
    assert m["dressing"] == "night_market" and m["version"] == 3
    assert m["environment"]["asset"] == "environments/market_square"
    assert m["workfile_rel"] == "x/publish/f.blend"
    assert m["props"][0]["object"] == "prop_root__lantern_1"
    # empty environment / props tolerated (manifest still well-formed)
    m2 = D.build_dressing_manifest("a", 1, None, None)
    assert m2["environment"] == {} and m2["props"] == []
