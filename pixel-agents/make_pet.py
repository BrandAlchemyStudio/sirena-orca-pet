"""Draw pixel Sirena for the Pixel Agents office (pet.png, 96x96).

Sirena, created by Anita (BrandAlchemyStudio). Art: CC BY-NC 4.0. Code: PolyForm
Noncommercial 1.0.0. Non-commercial use only; see ../LICENSE.
Every pixel is written below as a character grid; colours come from her
painted spritesheet. Run: python make_pet.py  -> assets/pets/sirena/pet.png
"""
from pathlib import Path

from PIL import Image

PAL = {
    "O": (138, 78, 34),     # hair outline
    "H": (226, 160, 72),    # honey-blonde hair
    "h": (250, 208, 125),   # hair highlight
    "d": (186, 116, 52),    # hair shade
    "S": (255, 208, 170),   # skin
    "s": (230, 165, 128),   # skin shade
    "k": (176, 106, 76),    # skin outline
    "E": (32, 86, 160),     # eye (blue)
    "c": (250, 150, 145),   # cheek
    "M": (200, 80, 90),     # mouth
    "B": (40, 112, 212),    # shell top
    "b": (18, 66, 150),     # shell top dark / straps
    "T": (36, 168, 236),    # tail
    "t": (14, 88, 170),     # tail outline / shade
    "P": (120, 140, 232),   # tail scale (lilac-blue)
    "F": (128, 236, 226),   # aquamarine fluke
    "f": (44, 170, 178),    # fluke outline
}

W1, H1 = 16, 32  # front/back frame
W2 = 32          # side frame


def grid(rows, w, h):
    """rows: {y: "pixels"} centred-left at x=0; '.' = transparent."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in rows.items():
        assert len(row) == w, (y, len(row), row)
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x, y), PAL[ch] + (255,))
    return img


def shift(rows, dy=0, dx=0, ys=None):
    """Move rows (all, or only those in ys) by dy/dx."""
    out = {}
    for y, row in rows.items():
        if ys is None or y in ys:
            if dx > 0:
                row = "." * dx + row[:-dx]
            elif dx < 0:
                row = row[-dx:] + "." * -dx
            out[y + dy] = row
        else:
            out[y] = row
    return out


def R(w, spec):
    """spec: {y: (x, "pixels")} -> {y: full-width row}."""
    out = {}
    for y, (x, px) in spec.items():
        row = "." * x + px
        assert len(row) <= w, (y, len(row))
        out[y] = row + "." * (w - len(row))
    return out


# ---------------- FRONT (facing viewer) ----------------
HEAD_FRONT = {
    8:  "......OOOO......",
    9:  "....OOhhHHOO....",
    10: "...OHhHHHHHdO...",
    11: "..OHhHHHHSSHdO..",
    12: "..OHHSSSSSSHHO..",
    13: "..OHHSESSESHHO..",
    14: "..OHHSESSESHHO..",
    15: "..OdHcSMMScHdO..",
    16: ".OHHHkSSSSkHHHO.",
    17: ".OHdHHHSSHHHdHO.",
    18: ".OHHSSSSSSSSHHO.",
    19: "OHdSSBBSSBBSSdHO",
    20: ".OHkSbBSSBbSkHO.",
    21: ".OHSkSSSSSSkSHO.",
    22: "..dSdtTTPTTtdSd.",
}
TAIL_FRONT = {
    23: ".....tTPTTt.....",
    24: ".....tTTPTt.....",
    25: "......tTTPt.....",
    26: "......tPTTt.....",
    27: "......fFtFf.....",
    28: ".....fFFfFFf....",
    29: "....fFFf.fFFf...",
    30: "...fff.....fff..",
}
TAIL_FRONT_L = {
    23: ".....tTPTTt.....",
    24: ".....tTTPTt.....",
    25: ".....tTTPt......",
    26: "....tPTTt.......",
    27: "...fFtFf........",
    28: "..fFFfFFf.......",
    29: ".fFFf.fFFf......",
    30: "fff.....fff.....",
}
TAIL_FRONT_R = {
    23: ".....tTPTTt.....",
    24: ".....tTTPTt.....",
    25: "......tTTPt.....",
    26: ".......tPTTt....",
    27: "........fFtFf...",
    28: ".......fFFfFFf..",
    29: "......fFFf.fFFf.",
    30: ".....fff.....fff",
}
TAIL_FRONT_FLICK = {**TAIL_FRONT,
    27: "......fFtFf.....",
    28: "....ffFFfFFff...",
    29: "...fFFf...fFFf..",
    30: "...ff.......ff..",
}

# ---------------- BACK (facing away) ----------------
def _back_hair():
    """Back of her head: the front silhouette, filled with S-shaped strands."""
    wave = [0, 0, 1, 1, 1, 0, 0, -1, -1, -1, 0, 0, 1, 1]
    pattern = "HhHHdH"
    rows = {}
    for y, row in HEAD_FRONT.items():
        out = []
        for x, ch in enumerate(row):
            if ch in "Hhd" or (8 < y < 19 and ch in "SEcMsk"):
                out.append(pattern[(x + wave[(y - 8) % len(wave)]) % len(pattern)])
            else:
                out.append(ch)
        rows[y] = "".join(out)
    rows.update({
        18: ".OHSdHhHHHdHSHO.",
        19: "OHdSbHHdHhHHbSdO",
        20: ".OHSkHhHHHdkSHO.",
        21: ".OHSkOHdOhdOkSHO"[:16],
        22: "..dSdtTTPTTtdSd.",
    })
    rows[21] = ".OHSkHdOHdOkSHO."
    return rows


HEAD_BACK = _back_hair()


def frame(*parts, dy=0):
    rows = {}
    for p in parts:
        rows.update(p)
    return grid(shift(rows, dy=dy), W1, H1)


front_idle = frame(HEAD_FRONT, TAIL_FRONT)
front_idle_flick = frame(HEAD_FRONT, TAIL_FRONT_FLICK)
front_idle_float = frame(HEAD_FRONT, TAIL_FRONT, dy=-1)
front_swim = [frame(HEAD_FRONT, TAIL_FRONT),
              frame(HEAD_FRONT, TAIL_FRONT_L, dy=-1),
              frame(HEAD_FRONT, TAIL_FRONT_R, dy=-1)]

back_idle = frame(HEAD_BACK, TAIL_FRONT)
back_idle_flick = frame(HEAD_BACK, TAIL_FRONT_FLICK)
back_idle_float = frame(HEAD_BACK, TAIL_FRONT, dy=-1)
back_swim = [frame(HEAD_BACK, TAIL_FRONT),
             frame(HEAD_BACK, TAIL_FRONT_R, dy=-1),
             frame(HEAD_BACK, TAIL_FRONT_L, dy=-1)]

# ---------------- SIDE (swimming right, 32x32) ----------------
SIDE_BODY = R(W2, {
    8:  (14, "OOOOO"),
    9:  (12, "OOhhHHHO"),
    10: (11, "OHhHHHHHHO"),
    11: (10, "OHHhHHHHSSk"),
    12: (10, "OHhHHHHHSSSk"),
    13: (9,  "OHHHhHHHSSESk"),
    14: (9,  "OHdHHhHHSSESSk"),
    15: (9,  "OHHdHHhHHScMk"),
    16: (9,  "OHhHHdHHHkSk"),
    17: (8,  "OHHhHHdHHHkSk"),
    18: (8,  "OdHHhHHdHkSSSSk"),
    19: (8,  "OHhHHdHHksSSSBBb"),
    20: (9,  "OHHhHdHksSSSbBb"),
    21: (10, "OdHOHdksSSSSk"),
    22: (15, "tTTPTTt"),
    23: (12, "ttTTPTTTTt"),
    24: (9,  "ttTTTPTTTPTt"),
    25: (7,  "tTTPTTTTTtt"),
    26: (6,  "tTTTPTtt"),
    27: (5,  "tTTtt"),
})
FLUKE_SIDE = R(W2, {
    0: (1, "ff"),
    1: (0, "fFFf"),
    2: (0, "fFFFff"),
    3: (0, "fFFFFt"),
    4: (0, "fFFFFFf"),
    5: (0, "fFFFff"),
    6: (1, "ff"),
})


def fluke_at(top):
    return {top + y: row for y, row in FLUKE_SIDE.items()}


SIDE_TAIL_MID = fluke_at(23)
SIDE_TAIL_UP = fluke_at(21)
SIDE_TAIL_DOWN = fluke_at(25)


def overlay(base, top):
    rows = dict(base)
    for y, row in top.items():
        under = rows.get(y, "." * len(row))
        rows[y] = "".join(t if t != "." else u for t, u in zip(row, under))
    return rows


def side(tail, dy=0):
    return grid(shift(overlay(SIDE_BODY, tail), dy=dy), W2, 32)


side_swim = [side(SIDE_TAIL_MID), side(SIDE_TAIL_UP, dy=-1), side(SIDE_TAIL_DOWN, dy=-1)]


def build():
    sheet = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    row0 = front_swim + [front_idle, front_idle_flick, front_idle_float]
    row1 = back_swim + [back_idle, back_idle_flick, back_idle_float]
    for i, im in enumerate(row0):
        sheet.paste(im, (i * 16, 0))
    for i, im in enumerate(row1):
        sheet.paste(im, (i * 16, 32))
    for i, im in enumerate(side_swim):
        sheet.paste(im, (i * 32, 64))
    return sheet


if __name__ == "__main__":
    out = Path(__file__).parent / "assets" / "pets" / "sirena"
    out.mkdir(parents=True, exist_ok=True)
    sheet = build()
    sheet.save(out / "pet.png", optimize=True)
    print("saved", out / "pet.png", sheet.size)
