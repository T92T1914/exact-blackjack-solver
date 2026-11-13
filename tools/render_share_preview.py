"""Render a compact sharing summary from maintained evidence, without an experiment."""

import argparse
import hashlib
import importlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONFIG_PATH = ROOT / "docs/sharing-card.json"
RECEIPT = ROOT / "docs/sharing-card-receipt.json"
# The card keeps the 2 to 1 shape of a repository social preview at the width of the wide
# Obscur edition. The type floor is 30 pt at 100 dpi, which is 41.67 px, so 42 px.
SIZE = (1800, 900)
MARGIN = 72
LIMIT = SIZE[0] - 2 * MARGIN
INSET = 12
FLOOR_PX = 42
PAD_Y = 40
GAP = 14


def digest(path):
    data = path.read_bytes()
    if path.suffix in (".py", ".json", ".md", ".css"):
        data = path.read_text(encoding="utf-8").encode()
    return hashlib.sha256(data).hexdigest()


def content(config):
    source = ROOT / config["source"]
    kind = config["kind"]
    if kind in ("freight", "timing", "solver"):
        helper = importlib.import_module("tools." + config["helper"])
        data = helper.load_data()
    if kind == "freight":
        panels = [
            ["Ridge model", f"{data['metrics']['model_mae']:.0f}", "moves / month"],
            ["Seasonal baseline", f"{data['metrics']['naive_mae']:.0f}", "moves / month"],
        ]
        context = "Mean absolute error | 24 synthetic test months"
        footer = "Prior observations used. Not operational forecasts."
    elif kind == "timing":
        panels = [
            ["Requests", str(data["request_count"]), "submitted"],
            ["Calculations", str(data["stats"]["computed"]), "executed"],
        ]
        context = "Controlled worker example"
        footer = "99 waiting requests replaced. 1 obsolete result rejected."
        if data["stats"]["replaced"] != 99 or data["stats"]["stale"] != 1:
            raise ValueError("Retained worker result changed")
    elif kind == "solver":
        names = {"H": "HIT", "S": "STAND"}
        panels = [
            [
                " + ".join("10" if c == "T" else c for c in hand["cards"]),
                names[hand["action"]],
                f"{hand['values'][hand['action']]:.6f} / original wager",
            ]
            for hand in data["hands"]
        ]
        context = "Both total 16 | Dealer shows 10 | Saved six-deck example"
        footer = "Original split path approximate. Bounded models have own limits."
    elif kind == "mcts":
        panels = [
            ["Same forest", "Sequential", "independent roots"],
            ["Same forest", "Parallel", "independent roots"],
        ]
        context = "Fixed seeds and work | Retained execution comparison"
        footer = "No general speedup or stronger-play claim."
    else:
        panels = [
            ["Source record", "Observation", "what is claimed"],
            ["Exact locator", "Source", "where to inspect it"],
        ]
        context = "Reviewed dossiers | Sources, creators and uncertainty"
        footer = "Source records remain distinct from unique tornadoes."
    return dict(
        title=config["title"],
        subtitle=config["subtitle"],
        panels=panels,
        context=context,
        footer=footer,
        source_sha256=digest(source),
    )


def roles(config):
    text = (ROOT / config["tokens"]).read_text(encoding="utf-8")
    if config["kind"] != "atlas":
        palette = json.loads(text)["themes"]["Obscur"]
        return palette
    values = dict(re.findall(r"--([a-z-]+):(#(?:[a-f0-9]{6}));", text.split("}", 1)[0]))
    return dict(
        canvas=values["bg"],
        panel=values["panel"],
        divider=values["line"],
        text=values["text"],
        muted=values["muted"],
        accent=values["text"],
    )


def font_files(config, directory):
    if config["helper"]:
        return importlib.import_module("tools." + config["helper"]).font_files(directory)
    from fontTools.ttLib import TTFont

    files, evidence = {}, {}
    for face, weight, italic in [
        ("Regular", 400, False),
        ("SemiBold", 600, False),
        ("Bold", 700, False),
    ]:
        path = directory / ("Inter-" + face + ".ttf")
        with TTFont(path) as font:
            name = font["name"].getDebugName(6)
            if (
                name != "Inter-" + face
                or font["OS/2"].usWeightClass != weight
                or bool(font["OS/2"].fsSelection & 1) != italic
                or not set(range(32, 127)).issubset(font.getBestCmap())
            ):
                raise ValueError("Wrong Inter face or missing authored glyph")
            evidence[face] = dict(
                postscript=name, weight=weight, italic=italic, sha256=digest(path)
            )
        files[face] = path
    return files, evidence


def inputs(config):
    names = [
        "tools/render_share_preview.py",
        "docs/sharing-card.json",
        config["source"],
        config["tokens"],
    ]
    if config["helper"]:
        names.append("tools/" + config["helper"] + ".py")
    return {name: digest(ROOT / name) for name in names}


def check():
    config = json.loads(CONFIG_PATH.read_text())
    receipt = json.loads(RECEIPT.read_text())
    if receipt["inputs_sha256_lf"] != inputs(config) or receipt["content"] != content(config):
        raise ValueError("Sharing evidence or renderer changed")
    data = (ROOT / config["output"]).read_bytes()
    if (
        hashlib.sha256(data).hexdigest() != receipt["png_sha256"]
        or data[:8] != b"\x89PNG\r\n\x1a\n"
        or struct.unpack(">II", data[16:24]) != SIZE
        or data[25] != 2
        or len(data) >= 1_000_000
    ):
        raise ValueError("Sharing PNG identity, dimensions, opacity or size differs")
    if (
        receipt["dimensions"] != list(SIZE)
        or not receipt["painted_labels"]
        or min(item["size"] for item in receipt["painted_labels"]) < FLOOR_PX
        or receipt["minimum_label_px"] < FLOOR_PX
        or receipt["floor_px"] != FLOOR_PX
    ):
        raise ValueError("Sharing labels are below the Obscur type floor")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        print("Sharing PNG matches retained content and renderer")
        return
    if args.font_dir is None:
        parser.error("--font-dir is required, no font is downloaded")
    from PIL import Image, ImageDraw, ImageFont, __version__

    config = json.loads(CONFIG_PATH.read_text())
    data, palette = content(config), roles(config)
    files, faces = font_files(config, args.font_dir)
    image = Image.new("RGB", SIZE, palette["canvas"])
    draw = ImageDraw.Draw(image)
    labels = []

    def wrapped(text, font, max_width):
        """Wrap by measured width. A word that does not fit means the layout must change."""
        lines = []
        for paragraph in text.split("\n"):
            current = ""
            for word in paragraph.split(" "):
                trial = f"{current} {word}" if current else word
                if font.getlength(trial) <= max_width:
                    current = trial
                elif not current:
                    raise ValueError("A word does not fit its line, change the layout: " + word)
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines

    def label(x, y, text, size, face="Regular", color=None, max_width=LIMIT, paint=True,
              box=None):
        """Paint wrapped lines from y down and return where the label ends."""
        if size < FLOOR_PX:
            raise ValueError("Sharing label is below the Obscur type floor: " + text)
        font = ImageFont.truetype(str(files[face]), size)
        lines = wrapped(text, font, max_width)
        for index, line in enumerate(lines):
            top = y + index * round(size * 1.3)
            bounds = draw.textbbox((x, top), line, font=font, anchor="lt")
            left, above, right, below = box or (0, 0, SIZE[0], SIZE[1])
            inset = INSET if box else MARGIN - 24
            if (
                bounds[0] < left + inset
                or bounds[1] < above + (INSET if box else 48)
                or bounds[2] > right - inset
                or bounds[3] > below - (INSET if box else 48)
            ):
                raise ValueError("Sharing label leaves its safe region: " + line)
            if paint:
                draw.text((x, top), line, font=font, fill=color or palette["text"], anchor="lt")
                labels.append(
                    dict(text=line, face="Inter-" + face, bounds=list(bounds), size=size)
                )
        return y + len(lines) * round(size * 1.3)

    y = label(MARGIN, 72, data["title"], 76, "Bold") + 14
    y = label(MARGIN, y, data["subtitle"], 46, "SemiBold", palette["accent"]) + 14
    y = label(MARGIN, y, data["context"], 42) + 48
    accents = [palette["accent"], palette.get("warning", palette["muted"])]
    if config["kind"] == "freight":
        series = json.loads((ROOT / config["tokens"]).read_text())["series"]
        accents = [series["model"]["obscur"], series["seasonal_naive"]["obscur"]]
    panel_width = (SIZE[0] - 2 * MARGIN - 48) // 2
    inner = panel_width - 56

    def value_size(value):
        return 88 if len(value) < 10 else 72

    def panel_height():
        total = 0
        for name, value, detail in data["panels"]:
            height = PAD_Y + 2 * GAP
            for text, size, face, width in (
                (name, 44, "SemiBold", inner),
                (value, value_size(value), "Bold", inner),
                (detail, 42, "Regular", inner),
            ):
                font = ImageFont.truetype(str(files[face]), size)
                height += len(wrapped(text, font, width)) * round(size * 1.3)
            total = max(total, height + PAD_Y)
        return total

    top, height = y, panel_height()
    for i, (name, value, detail) in enumerate(data["panels"]):
        x = MARGIN + i * (panel_width + 48)
        box = (x, top, x + panel_width, top + height)
        draw.rounded_rectangle(
            box, radius=18, fill=palette["panel"], outline=palette["divider"], width=2
        )
        inside = dict(max_width=inner, box=box)
        cursor = label(x + 28, top + PAD_Y, name, 44, "SemiBold", **inside) + GAP
        cursor = label(
            x + 28, cursor, value, value_size(value), "Bold", accents[i], **inside
        ) + GAP
        label(x + 28, cursor, detail, 42, **inside)
    y = top + height + 48
    end = label(MARGIN, y, data["footer"], 42, "SemiBold", palette["muted"])
    if end > SIZE[1] - 49:
        raise ValueError("The sharing footer leaves less than 49 px below it")
    output = ROOT / config["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    receipt = dict(
        schema_version=1,
        content=data,
        inputs_sha256_lf=inputs(config),
        png_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        dimensions=list(SIZE),
        floor_px=FLOOR_PX,
        minimum_label_px=min(item["size"] for item in labels),
        appearance="obscur",
        opaque=True,
        renderer={"Pillow": __version__},
        font_files=faces,
        painted_labels=labels,
        experimental_work_rerun=False,
        kind="authored summary, not an application screenshot",
    )
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    check()
    print("Rendered opaque Inter sharing summary from retained evidence")


if __name__ == "__main__":
    main()
