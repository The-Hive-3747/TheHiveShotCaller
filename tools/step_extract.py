"""Extract world placements of HIVE parts from the FTC field STEP (AP214-ish text).

Usage: python -I tools/step_extract.py [zip_path] [--pattern REGEX] [--max N]

Reads the STEP straight from the zip (nothing is extracted or executed), parses
entities into a dict, builds the assembly tree from NEXT_ASSEMBLY_USAGE_OCCURRENCE
+ CONTEXT_DEPENDENT_SHAPE_REPRESENTATION/ITEM_DEFINED_TRANSFORMATION chains, and
prints world origin/axes of every product instance whose name matches the pattern.
Units are whatever the file uses (printed; typically mm) and are also shown in inches.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import defaultdict

import numpy as np

ENT = re.compile(rb"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|ENDSEC)", re.S)


def load(zip_path: str) -> dict[int, tuple[str, str]]:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith((".step", ".stp")))
        data = z.read(name)
    ents: dict[int, tuple[str, str]] = {}
    sec = data.find(b"DATA;")
    for m in ENT.finditer(data, sec):
        body = m.group(2).decode("latin-1")
        body = re.sub(r"\s+", " ", body)
        if body.startswith("("):  # complex entity
            ents[int(m.group(1))] = ("COMPLEX", body)
            continue
        k = body.find("(")
        ents[int(m.group(1))] = (body[:k].strip(), body[k:])
    return ents


def refs(s: str) -> list[int]:
    return [int(x) for x in re.findall(r"#(\d+)", s)]


def strarg(s: str) -> str:
    m = re.match(r"\(\s*'((?:[^']|'')*)'", s)
    return m.group(1) if m else ""


def num_list(s: str) -> list[float]:
    m = re.search(r"\(\s*([-+0-9.eE, ]+)\)\s*\)?\s*$", s)
    return [float(x) for x in m.group(1).split(",")] if m else []


def axis_matrix(ents, aid: int) -> np.ndarray:
    """4x4 matrix of an AXIS2_PLACEMENT_3D (maps local -> parent)."""
    _, a = ents[aid]
    r = refs(a)
    loc = np.array(num_list(ents[r[0]][1]))
    z = np.array(num_list(ents[r[1]][1])) if len(r) > 1 else np.array([0, 0, 1.0])
    x = np.array(num_list(ents[r[2]][1])) if len(r) > 2 else None
    z = z / np.linalg.norm(z)
    if x is None:
        x = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = x - z * np.dot(x, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, loc
    return M


def build(ents):
    by = defaultdict(list)
    for i, (n, _) in ents.items():
        by[n].append(i)
    # product definition -> product name
    prod_name = {}
    pdf_to_prod = {}
    by["_REL"] = [i for i, (n, b) in ents.items()
                  if "REPRESENTATION_RELATIONSHIP" in (n if n != "COMPLEX" else b)
                  and "TRANSFORMATION" not in (n if n != "COMPLEX" else b)]
    for i in by["PRODUCT_DEFINITION_FORMATION"] + by["PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"]:
        r = refs(ents[i][1])
        if r:
            pdf_to_prod[i] = r[-1]
    for i in by["PRODUCT"]:
        prod_name[i] = strarg(ents[i][1])
    pd_name = {}
    for i in by["PRODUCT_DEFINITION"]:
        r = refs(ents[i][1])
        pdf = r[0] if r else None
        pd_name[i] = prod_name.get(pdf_to_prod.get(pdf), "?")
    # NAUO: id -> (parent pd, child pd, instance name)
    nauo = {}
    for i in by["NEXT_ASSEMBLY_USAGE_OCCURRENCE"]:
        r = refs(ents[i][1])
        nauo[i] = (r[0], r[1], strarg(ents[i][1]))
    # PRODUCT_DEFINITION_SHAPE -> definition (a pd or a nauo)
    pds_def = {}
    for i in by["PRODUCT_DEFINITION_SHAPE"]:
        r = refs(ents[i][1])
        pds_def[i] = r[0] if r else None
    # transforms: CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(rep_relationship, pds)
    # REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(name,desc,rep1,rep2,idt)
    xf = {}
    for i in by["CONTEXT_DEPENDENT_SHAPE_REPRESENTATION"]:
        rr, pds = refs(ents[i][1])[:2]
        target = pds_def.get(pds)
        rel = ents.get(rr)
        if target in nauo and rel:
            idt = refs(rel[1])[-1] if rel[0] != "COMPLEX" else None
            if rel[0] == "COMPLEX":
                idt = refs(rel[1])[-1]
            xf[target] = idt
    return by, pd_name, nauo, xf


def idt_matrix(ents, idt: int) -> np.ndarray:
    """ITEM_DEFINED_TRANSFORMATION(name, desc, item1, item2): maps item1 frame -> item2."""
    r = refs(ents[idt][1])
    A = axis_matrix(ents, r[0])
    B = axis_matrix(ents, r[1])
    return B @ np.linalg.inv(A)


def part_vertices(ents, by, pd: int, _cache: dict = {}) -> np.ndarray:  # noqa: B006
    """All B-rep vertex coordinates (file units) of a part definition, in its own frame."""
    cache = _cache
    if pd in cache:
        return cache[pd]
    sdr = None
    pds = None
    for i in by["PRODUCT_DEFINITION_SHAPE"]:
        if refs(ents[i][1])[:1] == [pd]:
            pds = i
            break
    for i in by["SHAPE_DEFINITION_REPRESENTATION"]:
        r = refs(ents[i][1])
        if pds is not None and r[0] == pds:
            sdr = r[1]
            break
    pts = []
    seen = set()
    stack = [sdr] if sdr else []
    if sdr:  # geometry usually lives in a representation linked by a *_RELATIONSHIP
        for i in by["_REL"]:
            r = refs(ents[i][1])
            if sdr in r:
                stack.extend(x for x in r if x != sdr)
    while stack:
        e = stack.pop()
        if e in seen or e not in ents:
            continue
        seen.add(e)
        name, a = ents[e]
        if name in ("MAPPED_ITEM", "REPRESENTATION_MAP"):
            continue
        if name == "VERTEX_POINT":
            pts.append(num_list(ents[refs(a)[0]][1]))
            continue
        stack.extend(refs(a))
    out = np.array(pts, float).reshape(-1, 3)
    cache[pd] = out
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", nargs="?", default="data/cad/field-cad-step.zip")
    ap.add_argument("--pattern", default=r"Bottom Skin|April Tag|Goal Rib|Cell|Hive")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--extents", action="store_true",
                    help="also print world-frame vertex bounding boxes (inches)")
    ap.add_argument("--summary", action="store_true",
                    help="print per-CELL derived numbers: rib extents, tag centers, beam coords")
    ap.add_argument("--frame", action="store_true",
                    help="print the HIVE frame (am-5854) part extents and centerline endpoints")
    ap.add_argument("--perimeter", action="store_true",
                    help="print perimeter / glass / tile extents (field inside size)")
    ap.add_argument("--names", action="store_true", help="only list distinct PRODUCT names")
    a = ap.parse_args(argv)
    ents = load(a.zip)
    print(f"entities: {len(ents)}")
    by, pd_name, nauo, xf = build(ents)
    print(f"products: {len(by['PRODUCT'])} nauo: {len(nauo)} with transform: {len(xf)}")
    # length unit: scan complex entities for LENGTH_UNIT (SI_UNIT($,.METRE.) = metres)
    U = 1.0 / 25.4
    for _, (n, body) in ents.items():
        if n == "COMPLEX" and "LENGTH_UNIT" in body:
            U = (1.0 / 0.0254) if ".MILLI." not in body else 1.0 / 25.4
            print("length unit:", body.strip()[:80], "-> inches factor", U)
            break
    pat = re.compile(a.pattern, re.I)
    if a.names:
        for n in sorted({v for v in pd_name.values() if pat.search(v)}):
            print(n)
        return 0
    children = defaultdict(list)
    parents = defaultdict(list)
    for n, (p, c, _nm) in nauo.items():
        children[p].append((n, c))
        parents[c].append((n, p))
    roots = [pd for pd in pd_name if pd not in parents]
    print("roots:", [pd_name[r] for r in roots][:5])
    found = 0

    def walk(pd, M, path):
        nonlocal found
        name = pd_name[pd]
        if pat.search(name) and found < a.max:
            found += 1
            o = M[:3, 3]
            print(f"{'/'.join(path[-3:])}/{name}: origin_in={(o * U).round(3).tolist()} "
                  f"x={M[:3, 0].round(4).tolist()} y={M[:3, 1].round(4).tolist()} "
                  f"z={M[:3, 2].round(4).tolist()}")
            if a.extents:
                v = part_vertices(ents, by, pd)
                if len(v):
                    w = (M[:3, :3] @ v.T).T + M[:3, 3]
                    print(f"    vertices={len(v)} world_min_in={(w.min(0) * U).round(2).tolist()} "
                          f"world_max_in={(w.max(0) * U).round(2).tolist()}")
                    loc = v
                    print(f"    local_min_in={(loc.min(0) * U).round(2).tolist()} "
                          f"local_max_in={(loc.max(0) * U).round(2).tolist()}")
        for n, c in children.get(pd, []):
            T = idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
            walk(c, M @ T, path + [name])

    sys.setrecursionlimit(10000)
    if a.summary:
        return summary(ents, by, pd_name, children, roots, xf, U)
    if a.frame or a.perimeter:
        return frame_report(ents, by, pd_name, children, roots, xf, U, a.frame, a.perimeter)
    for r in roots:
        walk(r, np.eye(4), [])
    return 0


def _axis_endpoints(w: np.ndarray):
    """Principal-axis centerline endpoints of a roughly bar-like vertex cloud (world units)."""
    c = w.mean(0)
    _, _, vt = np.linalg.svd(w - c, full_matrices=False)
    ax = vt[0]
    t = (w - c) @ ax
    return c + ax * t.min(), c + ax * t.max(), ax


def frame_report(ents, by, pd_name, children, roots, xf, U, do_frame, do_perim) -> int:
    """CAD frame (x lateral, y up, z along the beam), inches."""
    rows = []

    def walk(pd, M, path):
        name = pd_name[pd]
        v = part_vertices(ents, by, pd)
        if len(v):
            w = ((M[:3, :3] @ v.T).T + M[:3, 3]) * U
            rows.append((path, name, w))
        for n, c in children.get(pd, []):
            T = idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
            walk(c, M @ T, path + [name])

    for r in roots:
        if "BIOBUZZ" in pd_name[r]:
            walk(r, np.eye(4), [])
    if do_frame:
        print("== HIVE frame (am-5854) parts: world min / max / centerline endpoints / axis")
        for path, name, w in rows:
            if not any(p.startswith("am-5854") for p in path):
                continue
            if not any(k in name for k in ("Leg", "Foot", "Top Bar", "Top Corner", "Axle", "Under Tile",
                                           "Panel", "Sticker")):
                continue
            a0, a1, ax = _axis_endpoints(w)
            print(f"{name}: min={w.min(0).round(2).tolist()} max={w.max(0).round(2).tolist()} "
                  f"end0={a0.round(2).tolist()} end1={a1.round(2).tolist()} axis={ax.round(3).tolist()}")
    if do_perim:
        print("== perimeter / glass / tiles: world min / max (inches)")
        groups = defaultdict(list)
        for path, name, w in rows:
            for key in ("Perimeter", "Riveted FTC Panel", "Side Glass", "Soft Tiles", "FTC Rail", "Panel Link"):
                if key in name or any(key in p for p in path):
                    groups[key].append(w)
        for key, ws in groups.items():
            allw = np.vstack(ws)
            print(f"{key}: parts={len(ws)} min={allw.min(0).round(3).tolist()} max={allw.max(0).round(3).tolist()}")
    return 0


def summary(ents, by, pd_name, children, roots, xf, U) -> int:
    """CAD frame here is x lateral, y UP, z along the beam (audience = +z). Beam
    coordinates relative to the pivot (y=43.95): a = z cos30 + (y-43.95) sin30 for the
    audience-up state; b = -z sin30 + (y-43.95) cos30."""
    pivot_y = 43.95
    c30, s30 = np.cos(np.radians(30)), np.sin(np.radians(30))
    rows = []

    def walk(pd, M, path):
        name = pd_name[pd]
        cell = next((p for p in reversed(path) if "Cell (" in p), None)
        if cell and ("Goal Rib" in name or "April Tag" in name or "Bottom Skin" in name):
            v = part_vertices(ents, by, pd)
            if len(v):
                w = ((M[:3, :3] @ v.T).T + M[:3, 3]) * U
                rows.append((cell, name, w))
        for n, c in children.get(pd, []):
            T = idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
            walk(c, M @ T, path + [name])

    for r in roots:
        if "BIOBUZZ" in pd_name[r]:
            walk(r, np.eye(4), [])
    for cell in sorted({r[0] for r in rows}):
        print(f"== {cell}")
        ribs = np.vstack([w for c, n, w in rows if c == cell and "Goal Rib" in n])
        print(f"  Goal Ribs: world y(up) min={ribs[:, 1].min():.3f} max={ribs[:, 1].max():.3f}  "
              f"z min={ribs[:, 2].min():.3f} max={ribs[:, 2].max():.3f}  "
              f"x min={ribs[:, 0].min():.3f} max={ribs[:, 0].max():.3f}")
        for c, n, w in rows:
            if c == cell and ("April Tag" in n or "Bottom Skin" in n):
                ctr = (w.min(0) + w.max(0)) / 2
                a_ = ctr[2] * c30 + (ctr[1] - pivot_y) * s30
                b_ = -ctr[2] * s30 + (ctr[1] - pivot_y) * c30
                print(f"  {n}: bbox center x,y,z = {ctr.round(3).tolist()} "
                      f"(a,b audience-up frame) = ({a_:.3f}, {b_:.3f}) "
                      f"size = {(w.max(0) - w.min(0)).round(3).tolist()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
