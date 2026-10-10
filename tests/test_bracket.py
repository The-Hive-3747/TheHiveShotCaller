"""Tests for the tripod bracket generator (tools/make_bracket.py)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
trimesh = pytest.importorskip("trimesh")


@pytest.fixture(scope="module")
def mb():
    spec = importlib.util.spec_from_file_location(
        "make_bracket", ROOT / "tools" / "make_bracket.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_bracket"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mesh(mb):
    return mb.build()


def test_mesh_is_watertight(mesh):
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.is_volume


def test_volume_in_range(mesh):
    assert 15.0 < mesh.volume / 1000.0 < 60.0


def test_bounding_box(mesh):
    # 44 wide, 50 tall; depth = 40 base + 4 plate (+3 mm standoff bosses on the camera face)
    assert np.allclose(mesh.extents, [44.0, 44.0 + 3.0, 50.0], atol=1.0)
    assert mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6)  # sits on the bed


def _overlap_volume(mesh, probe):
    """Volume of the part inside a probe solid (0 if the probe sits in empty space)."""
    try:
        inter = trimesh.boolean.intersection([mesh, probe], engine="manifold")
    except Exception:  # an empty result may raise depending on the backend
        return 0.0
    return float(abs(inter.volume)) if len(inter.faces) else 0.0


def _probe(center, extents):
    return trimesh.creation.box(
        extents=extents, transform=trimesh.transformations.translation_matrix(center)
    )


def test_features_present(mesh, mb):
    # 7 mm nut through hole: a 4 mm square column through the base centre is empty
    cy = mb.BASE_D / 2.0
    assert _overlap_volume(mesh, _probe([0, cy, mb.BASE_T / 2], [4, 4, mb.BASE_T])) < 1e-6
    # hex pocket: the region 5.5-ish mm off axis, just above the bed, is empty ...
    assert _overlap_volume(mesh, _probe([5.0, cy, 2.0], [1.0, 1.0, 2.0])) < 1e-6
    # ... but solid above the pocket ceiling
    assert _overlap_volume(mesh, _probe([5.0, cy, mb.BASE_T - 0.4], [1.0, 1.0, 0.8])) > 0.5
    # 20 mm lens clearance hole is open along Y through the board centre
    assert _overlap_volume(mesh, _probe([0, -2, mb.BOARD_CZ], [12, 4, 12])) < 1e-6
    # plate is solid just outside the lens hole
    z = mb.BOARD_CZ - mb.LENS_HOLE_D / 2.0 - 3.0
    assert _overlap_volume(mesh, _probe([0, -2, z], [4, 3, 2])) > 20.0
    # USB notch is open at the top edge
    assert _overlap_volume(mesh, _probe([0, -2, mb.TOTAL_H - 1.0], [10, 3, 1.5])) < 1e-6


def test_stl_written(mb, mesh, tmp_path):
    out = tmp_path / "b.stl"
    mesh.export(out, file_type="stl")
    assert out.stat().st_size > 10_000
    assert mb.STL_PATH.exists() and mb.STL_PATH.stat().st_size > 10_000
    reloaded = trimesh.load(mb.STL_PATH)
    assert reloaded.is_watertight
