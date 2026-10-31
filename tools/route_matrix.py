#!/usr/bin/env python3
"""Route F.Cu matrix row nets with left/right mirrored geometry.

Routes only: P6, P29, P4, P5, P28 on F.Cu.
  - P6/P29 computed on the left, mirrored to P4/P5 on the right
  - P28 (thumb) forced through the board centerline
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pcbnew

TRACK_W_MM = 0.25
F_CU = pcbnew.F_Cu

# Left nets are authored; right nets are mirrors.
PAIR_LEFT_TO_RIGHT = {
    "P29": "P5",  # top rows
    "P6": "P4",  # home rows
}
THUMB_NET = "P28"


def mm(v: float) -> int:
    return int(round(pcbnew.FromMM(v)))


def to_mm(v: int) -> float:
    return pcbnew.ToMM(v)


def vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def pad_xy(pad: pcbnew.PAD) -> tuple[float, float]:
    p = pad.GetPosition()
    return to_mm(p.x), to_mm(p.y)


def pad_ref(pad: pcbnew.PAD) -> str:
    if hasattr(pad, "GetParentAsString"):
        return pad.GetParentAsString() or ""
    return ""


def strip_copper_file(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text.startswith("\t(segment", i) or text.startswith("\t(via", i):
            depth = 0
            j = i
            while j < n:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        if j < n and text[j] == "\n":
                            j += 1
                        break
                j += 1
            i = j
            continue
        out.append(text[i])
        i += 1
    Path(path).write_text("".join(out), encoding="utf-8")


def ensure_d5_p28(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    idx = text.find('(property "Reference" "D5"')
    if idx < 0:
        return
    p2 = text.find('(pad "2"', idx)
    p3 = text.find('(pad "3"', p2)
    chunk = text[p2:p3]
    if '(net "P28")' in chunk:
        return
    chunk = chunk.replace(
        '(layers "F.Cu" "F.Mask" "F.Paste")\n',
        '(layers "F.Cu" "F.Mask" "F.Paste")\n\t\t\t(net "P28")\n',
        1,
    )
    Path(path).write_text(text[:p2] + chunk + text[p3:], encoding="utf-8")


def add_track(
    board: pcbnew.BOARD,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    netcode: int,
) -> None:
    if abs(x1 - x2) < 1e-7 and abs(y1 - y2) < 1e-7:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(vec(x1, y1))
    track.SetEnd(vec(x2, y2))
    track.SetWidth(mm(TRACK_W_MM))
    track.SetLayer(F_CU)
    track.SetNetCode(netcode)
    board.Add(track)


def poly_line(
    board: pcbnew.BOARD, pts: list[tuple[float, float]], netcode: int
) -> None:
    for a, b in zip(pts, pts[1:]):
        add_track(board, a[0], a[1], b[0], b[1], netcode)


def mirror_x(x: float, mid: float) -> float:
    return 2.0 * mid - x


def mirror_pts(
    pts: list[tuple[float, float]], mid: float
) -> list[tuple[float, float]]:
    return [(mirror_x(x, mid), y) for x, y in pts]


def find_pads(
    board: pcbnew.BOARD, net: str
) -> tuple[pcbnew.PAD | None, pcbnew.PAD | None]:
    diode = mcu = None
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != net:
                continue
            ref = pad_ref(pad)
            if ref.startswith("D"):
                diode = pad
            elif ref == "MCU1":
                mcu = pad
    return diode, mcu


def _dedup(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 1e-7 or abs(p[1] - out[-1][1]) > 1e-7:
            out.append(p)
    return out


def radial_escape(
    pad_xy: tuple[float, float],
    fp_xy: tuple[float, float],
    dist: float = 2.5,
) -> tuple[float, float]:
    """Step away from footprint center so the stub clears sibling SMD pads."""
    dx, dy = pad_xy[0] - fp_xy[0], pad_xy[1] - fp_xy[1]
    elen = math.hypot(dx, dy) or 1.0
    return pad_xy[0] + dx / elen * dist, pad_xy[1] + dy / elen * dist


def finger_row_path(
    diode_xy: tuple[float, float],
    mcu_xy: tuple[float, float],
    highway_y: float,
    jog_x: float,
    escape_xy: tuple[float, float],
) -> list[tuple[float, float]]:
    """diode → radial escape → highway → jog → MCU pad."""
    dx, dy = diode_xy
    ex, ey = escape_xy
    mx, my = mcu_xy
    pts = [
        (dx, dy),
        (ex, ey),
        (ex, highway_y),
        (jog_x, highway_y),
        (jog_x, my),
        (mx, my),
    ]
    return _dedup(pts)


def thumb_row_path(
    diode_xy: tuple[float, float],
    mcu_xy: tuple[float, float],
    mid_x: float,
    highway_y: float,
    escape_xy: tuple[float, float],
    clear_x: float,
    clear_y: float,
) -> list[tuple[float, float]]:
    """D5 → radial escape → north of thumb switches → toward mid → highway → center → MCU."""
    dx, dy = diode_xy
    ex, ey = escape_xy
    mx, my = mcu_xy
    pts = [
        (dx, dy),
        (ex, ey),
        (ex, clear_y),
        (clear_x, clear_y),
        (clear_x, highway_y),
        (mid_x, highway_y),
        (mid_x, my),
        (mx, my),
    ]
    return _dedup(pts)


def route_board(board: pcbnew.BOARD) -> None:
    mcu_fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == "MCU1")
    mid_x = to_mm(mcu_fp.GetPosition().x)

    # Highways inside the outline (pitch ≥ 0.9 mm), between diodes and MCU / thumbs.
    # top_hwy just below top diodes (~164); keeps ≥0.25 mm from S8/S16 NPTH (~169.8)
    top_hwy = 166.2
    home_hwy = 195.0
    thumb_hwy = 210.0
    thumb_clear_y = 218.0  # between S17 (~212) and D5 (~229), clears S18 at y≈227.7

    fp_pos = {
        fp.GetReference(): (to_mm(fp.GetPosition().x), to_mm(fp.GetPosition().y))
        for fp in board.GetFootprints()
    }

    left_jogs = {
        "P29": mid_x - 10.0,
        "P6": mid_x - 11.2,
    }
    left_hwys = {
        "P29": top_hwy,
        "P6": home_hwy,
    }
    left_diode_ref = {"P29": "D2", "P6": "D1"}

    for left_net, right_net in PAIR_LEFT_TO_RIGHT.items():
        d_l, m_l = find_pads(board, left_net)
        d_r, m_r = find_pads(board, right_net)
        if not d_l or not m_l or not d_r or not m_r:
            raise RuntimeError(f"missing pads for {left_net}/{right_net}")

        dxy = pad_xy(d_l)
        esc = radial_escape(dxy, fp_pos[left_diode_ref[left_net]])
        path_l = finger_row_path(
            dxy,
            pad_xy(m_l),
            left_hwys[left_net],
            left_jogs[left_net],
            esc,
        )
        path_r = mirror_pts(path_l, mid_x)
        path_r[0] = pad_xy(d_r)
        path_r[-1] = pad_xy(m_r)

        poly_line(board, path_l, m_l.GetNetCode())
        poly_line(board, path_r, m_r.GetNetCode())

        print(f"{left_net}: {len(path_l)-1} segs  |  {right_net} (mirror): {len(path_r)-1} segs")

    d_t, m_t = find_pads(board, THUMB_NET)
    if not d_t or not m_t:
        raise RuntimeError("missing pads for P28")
    dxy = pad_xy(d_t)
    esc = radial_escape(dxy, fp_pos["D5"], dist=2.5)
    # Jog toward midline past S17 NPTH (~174.6, 213) before dropping to the highway.
    clear_x = mid_x - 25.0  # ~194.5, gap between left thumbs and center
    path_t = thumb_row_path(
        dxy, pad_xy(m_t), mid_x, thumb_hwy, esc, clear_x, thumb_clear_y
    )
    poly_line(board, path_t, m_t.GetNetCode())
    print(f"{THUMB_NET} (centered): {len(path_t)-1} segs  mid_x={mid_x:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcb", nargs="?", default="board/kicad/kicad.kicad_pcb")
    args = ap.parse_args()

    strip_copper_file(args.pcb)
    ensure_d5_p28(args.pcb)
    board = pcbnew.LoadBoard(args.pcb)
    route_board(board)
    board.Save(args.pcb)

    n_tracks = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)
    n_vias = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    print(f"Wrote {n_tracks} tracks and {n_vias} vias to {args.pcb}")


if __name__ == "__main__":
    main()
