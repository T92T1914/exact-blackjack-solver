"""Render retained PR48 work versus its cap without running the solver."""

import argparse
import hashlib
import json
import math
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .presentation import OBSCUR_REVISION, TOKEN_REVISION, load_tokens
    from .render_composition_figure import (
        FACES, FLOOR_POINTS_AT_100_DPI, INSET, floor_points, font_files, wrap_text)
except ImportError:
    from render_composition_figure import (
        FACES, FLOOR_POINTS_AT_100_DPI, INSET, floor_points, font_files, wrap_text)

    from presentation import OBSCUR_REVISION, TOKEN_REVISION, load_tokens

ROOT = Path(__file__).resolve().parents[1]
DATA = "docs/ace-terminal-reuse.md"
REQUEST = "examples/bounded-ace-resplit-h17-request.json"
MANIFEST = "docs/ace-terminal-reuse-figure.json"
STEM = "ace-terminal-reuse"
REVISION = "3cbc80c5ce81d5a806f4fa3de8b30b04665f33c8"
SOURCE_SHA256 = "310e8949f7448671468d8ae7bba3d8b2af7ed9c0fb56131cb296a0993a00fcb1"
REQUEST_SHA256 = "8fc3c209a9f65fd87b4ee2cdda8aa6d57456c7748aea57331fe4f26892436cb4"
REPOSITORY = "T92T1914/exact-blackjack-solver"
GUIDE = f"https://github.com/{REPOSITORY}/blob/{REVISION}/{DATA}"
INPUTS = (
    DATA,
    REQUEST,
    "presentation/tokens.json",
    "tools/presentation.py",
    "tools/render_composition_figure.py",
    "tools/render_evidence_figure.py",
)
WIDTH, DPI = 1440, 120
# The retained Clair edition keeps its first canvas. The Obscur height follows its text.
CLAIR_HEIGHT = 720
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
DC = "http://purl.org/dc/elements/1.1/"
CC = "http://creativecommons.org/ns#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS = {"s": SVG}
RETAINED_CLAIR = tuple(f"docs/{STEM}-clair.{ext}" for ext in ("png", "svg"))
TITLE = "H17 request completed"
DESCRIPTION = (
    "One retained cold H17 ace-resplit request entered 82,780 numerical states "
    "under its unchanged 100,000-state cap. All four values and the original "
    "recommendation were preserved. This is work versus a budget boundary, "
    "not a timing improvement or a guarantee for every shoe."
)


def digest(path, text=False):
    data = path.read_text(encoding="utf-8").encode() if text else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def source_record():
    return {
        "repository": REPOSITORY,
        "revision": REVISION,
        "path": DATA,
        "url": GUIDE,
        "sha256": digest(ROOT / DATA, text=True),
    }


def request_record():
    if digest(ROOT / REQUEST, text=True) != REQUEST_SHA256:
        raise ValueError("Retained PR48 request changed; review before rendering")
    request = json.loads((ROOT / REQUEST).read_text(encoding="utf-8"))
    return {
        "path": REQUEST,
        "sha256": REQUEST_SHA256,
        "schema": request["schema"],
        "model": request["model"],
        "rules": request["rules"],
        "input": request["input"],
        "complete_actions": ["S", "H", "D", "P"],
    }


def load_values():
    if digest(ROOT / DATA, text=True) != SOURCE_SHA256:
        raise ValueError("Retained PR48 guide changed; review before rendering")
    guide = (ROOT / DATA).read_text(encoding="utf-8")
    match = re.search(
        r"Actual\s+entered and attempted work was ([0-9,]+) states\.", guide
    )
    if match is None or "completed all four action values" not in guide:
        raise ValueError("The explicit complete cold work observation is missing")
    request_record()
    request = json.loads((ROOT / REQUEST).read_text(encoding="utf-8"))
    entered = int(match.group(1).replace(",", ""))
    cap = request["limits"]["max_states"]
    if type(cap) is not int or not 0 < entered < cap:
        raise ValueError("The work observation must remain below its request cap")
    return {
        "entered_states": entered,
        "state_cap": cap,
        "action_count": 4,
        "one_cold_request": True,
    }


def add_svg_accessibility(path):
    for prefix, uri in (("", SVG), ("xlink", XLINK), ("dc", DC), ("cc", CC), ("rdf", RDF)):
        ET.register_namespace(prefix, uri)
    # Keep the comments. Outlined labels carry their text there.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(path, parser)
    root = tree.getroot()
    root.set("role", "img")
    root.set("aria-labelledby", "evidence-title evidence-description")
    ET.SubElement(root, f"{{{SVG}}}title", {"id": "evidence-title"}).text = TITLE
    ET.SubElement(root, f"{{{SVG}}}desc", {"id": "evidence-description"}).text = DESCRIPTION
    group = root.find(".//s:g[@id='source-link']", NS)
    if group is None:
        raise ValueError("The visible source link is missing")
    anchor = ET.Element(f"{{{SVG}}}a", {"href": GUIDE, "aria-label": "Source guide"})
    for child in list(group):
        group.remove(child)
        anchor.append(child)
    group.append(anchor)
    # Receipts bind delivered bytes, including line endings on every host.
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(payload.replace(b"\r\n", b"\n"))


def draw(values, tokens, mode, files, output):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import rc_context
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    roles = tokens["themes"][mode.capitalize()]
    fonts = {name: FontProperties(fname=str(path)) for name, path in files.items()}
    floor = floor_points(DPI)
    margin = 72
    limit = WIDTH - 2 * margin
    scale = 0.85 * WIDTH
    left = 0.07 * WIDTH
    bar_width = scale * values["entered_states"] / 112000
    cap_x = left + scale * values["state_cap"] / 112000

    def build(fig, height):
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, WIDTH)
        ax.set_ylim(height, 0)
        ax.axis("off")
        renderer = FigureCanvasAgg(fig).get_renderer()
        labels = []

        def put(x, top, text, points, face="Regular", gid=None, color=None, ha="left",
                wrap=False):
            if points < floor:
                raise ValueError("A retained-evidence label is below the Obscur type floor")
            prop = fonts[face].copy()
            prop.set_size(points)
            if wrap:
                text = wrap_text(renderer, prop, text, limit)
            item = ax.text(x, top, text, fontproperties=prop, color=color or roles["text"],
                           va="top", ha=ha, linespacing=1.3, gid=gid, zorder=3)
            labels.append(item)
            return item

        def extent(item):
            box = item.get_window_extent(renderer)
            return box.x0, height - box.y1, box.x1, height - box.y0

        title = put(margin, margin, TITLE, 38, "Bold")
        first = put(margin, extent(title)[3] + 16, "One cold AA / dealer A request. H17 and DAS.",
                    26)
        second = put(margin, extent(first)[3] + 4,
                     "All four values. Original recommendation preserved.", 26)
        cap_label = put(cap_x, extent(second)[3] + 28, f"{values['state_cap']:,} cap", 26,
                        "SemiBold", gid="state-cap-value", ha="center")
        bar_top = extent(cap_label)[3] + 14
        bar_height = 84
        ax.add_artist(Rectangle(
            (left, bar_top), bar_width, bar_height, facecolor=roles["accent"],
            gid="entered-states-bar", zorder=1))
        ax.add_artist(Line2D(
            (cap_x, cap_x), (bar_top - 10, bar_top + bar_height + 10),
            color=roles["warning"], linewidth=2 * 72 / DPI, linestyle="--", zorder=2))
        entered = put(left + bar_width / 2, bar_top, f"{values['entered_states']:,}", 30,
                      "Bold", gid="entered-states-value", color=roles["on_accent"], ha="center")
        entered.set_y(bar_top + (bar_height - (extent(entered)[3] - extent(entered)[1])) / 2)
        axis_top = bar_top + bar_height + 16
        zero = put(left, axis_top, "0", 25)
        axis_name = put(0.31 * WIDTH, axis_top, "Entered numerical states", 25)
        cursor = max(extent(zero)[3], extent(axis_name)[3]) + 34
        note = put(margin, cursor, "Reuse only terminal dealer outcomes. "
                   "Other shoes can refuse.", 25, wrap=True)
        work = put(margin, extent(note)[3] + 14, "Work versus cap, not a timing comparison.", 25)
        source = put(margin, extent(work)[3] + 14, "Retained PR48 result. Source guide.", 25,
                     gid="source-link")
        return labels, extent, extent(source)[3] + 49

    with rc_context({"svg.fonttype": "path", "svg.hashsalt": "solver-pr48-evidence-v1"}):
        scratch = Figure(figsize=(WIDTH / DPI, 3000 / DPI), dpi=DPI)
        height = math.ceil(build(scratch, 3000)[2])
        fig = Figure(figsize=(WIDTH / DPI, height / DPI), dpi=DPI, facecolor=roles["canvas"])
        labels, extent, _ = build(fig, height)
        FigureCanvasAgg(fig).draw()
        boxes = [extent(item) for item in labels]
        if any(b[0] < INSET or b[1] < INSET or b[2] > WIDTH - INSET or b[3] > height - INSET
               for b in boxes):
            raise ValueError("A retained-evidence label extends outside the canvas")
        minimum = min(item.get_fontsize() for item in labels)
        layout = {
            "width": WIDTH, "height": height, "dpi": DPI, "labels_within_canvas": len(boxes),
            "minimum_font_points": minimum,
            "minimum_font_points_at_100_dpi": minimum * DPI / 100,
            "floor_points_at_100_dpi": FLOOR_POINTS_AT_100_DPI,
            "minimum_inset_px": INSET,
        }
        for extension in ("png", "svg"):
            metadata = {"Description": json.dumps(values, sort_keys=True)}
            if extension == "svg":
                metadata["Date"] = None
            path = output / f"{STEM}-{mode}.{extension}"
            fig.savefig(path, metadata=metadata)
            if extension == "svg":
                add_svg_accessibility(path)
        fig.clear()
        return layout


def check_outputs():
    """Check retained source and committed exports without a plotting dependency."""
    record = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    values = load_values()
    if (
        record["schema_version"] != 1 or record["source_commit"] != REVISION
        or record["source"] != source_record() or record["values"] != values
        or record["request"] != request_record()
        or record["source_sha256_lf"]
        != {name: digest(ROOT / name, text=True) for name in INPUTS}
        or set(record["editions"]) != {"clair", "obscur"}
    ):
        raise ValueError("Retained figure source, values or renderer changed")
    themes = load_tokens()["themes"]
    if (
        record["rendering"]["theme_roles"]
        != {mode: themes[mode.capitalize()] for mode in ("clair", "obscur")}
        or record["rendering"]["new_measurement"] is not False
        or record["typography"]["font_binaries_distributed"] is not False
        or set(record["typography"]["files"]) != set(FACES)
        or {name: item["sha256"] for name, item in record["retained_clair"]["files"].items()}
        != {name: digest(ROOT / name) for name in RETAINED_CLAIR}
    ):
        raise ValueError("Figure appearance or font provenance changed")
    for face, (weight, italic) in FACES.items():
        evidence = record["typography"]["files"][face]
        checksum = evidence["sha256"]
        if (
            evidence["postscript"] != f"Inter-{face}"
            or evidence["weight"] != weight or evidence["italic"] is not italic
            or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum)
        ):
            raise ValueError("Validated static Inter identity changed")
    layout = record["layout"]["obscur"]
    if (
        layout["width"] != WIDTH or layout["dpi"] != DPI
        or layout["floor_points_at_100_dpi"] != FLOOR_POINTS_AT_100_DPI
        or layout["minimum_font_points_at_100_dpi"] < FLOOR_POINTS_AT_100_DPI
        or layout["minimum_font_points"] < floor_points(DPI)
    ):
        raise ValueError("The Obscur edition is below the type floor")
    for mode, edition in record["editions"].items():
        height = CLAIR_HEIGHT if mode == "clair" else layout["height"]
        if set(edition) != {"png", "svg"}:
            raise ValueError("Both PNG and SVG exports are required")
        for extension, item in edition.items():
            name = f"docs/{STEM}-{mode}.{extension}"
            path = ROOT / name
            if item["path"] != name or digest(path) != item["sha256"]:
                raise ValueError(f"Retained export changed: {name}")
            if extension == "png":
                raw = path.read_bytes()
                if raw[:8] != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("Invalid PNG signature")
                if struct.unpack_from(">II", raw, 16) != (WIDTH, height):
                    raise ValueError("PNG dimensions changed")
                if (item["width"], item["height"]) != (WIDTH, height):
                    raise ValueError("Manifest PNG dimensions changed")
                offset, descriptions = 8, []
                while offset + 12 <= len(raw):
                    length = struct.unpack_from(">I", raw, offset)[0]
                    end = offset + length + 12
                    if end > len(raw):
                        raise ValueError("Truncated PNG chunk")
                    if raw[offset + 4:offset + 8] == b"tEXt":
                        key, text = raw[offset + 8:end - 4].split(b"\0", 1)
                        if key == b"Description":
                            descriptions.append(json.loads(text.decode("latin-1")))
                    offset = end
                if descriptions != [values]:
                    raise ValueError("PNG retained values changed")
            else:
                parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
                svg = ET.parse(path, parser).getroot()
                box = [float(v) for v in svg.attrib["viewBox"].split()]
                if box != [0, 0, WIDTH * 72 / DPI, height * 72 / DPI]:
                    raise ValueError("SVG dimensions changed")
                if (
                    svg.get("width") != f"{WIDTH * 72 / DPI:g}pt"
                    or svg.get("height") != f"{height * 72 / DPI:g}pt"
                    or svg.get("role") != "img"
                    or svg.get("aria-labelledby") != "evidence-title evidence-description"
                ):
                    raise ValueError("SVG dimensions or accessible role changed")
                outlined = mode == "obscur"
                if (
                    svg.find("s:title", NS).text != TITLE
                    or svg.find("s:desc", NS).text != DESCRIPTION
                    or bool(svg.findall(".//s:text", NS)) is outlined
                    or svg.find(".//s:a", NS).get("href") != GUIDE
                    or json.loads(svg.find(f".//{{{DC}}}description").text) != values
                ):
                    raise ValueError("SVG accessible text or retained values changed")
                # The labels of the Obscur edition are outlines. Their text is the comment
                # that the renderer keeps in each group, read here against the source data.
                for gid, expected in (
                    ("entered-states-value", f"{values['entered_states']:,}"),
                    ("state-cap-value", f"{values['state_cap']:,} cap"),
                ):
                    group = svg.find(f".//s:g[@id='{gid}']", NS)
                    if group is None:
                        raise ValueError("Visible SVG work or cap changed")
                    if outlined:
                        shown = "".join(
                            child.text.strip() for child in group.iter() if child.tag is ET.Comment
                        )
                    else:
                        shown = "".join(group.itertext()).strip()
                    if shown != expected:
                        raise ValueError("Visible SVG work or cap changed")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, help="The three official static Inter TTFs")
    parser.add_argument("--check", action="store_true", help="Check without rendering")
    args = parser.parse_args()
    if args.check:
        check_outputs()
        print("Both PR48 editions match retained source and exported values")
        return
    if args.font_dir is None:
        parser.error("--font-dir is required; fonts are never downloaded")
    values, tokens = load_values(), load_tokens()
    files, evidence = font_files(args.font_dir)
    with tempfile.TemporaryDirectory(prefix="solver-evidence-") as directory:
        output = Path(directory)
        layout = {"obscur": draw(values, tokens, "obscur", files, output)}
        import matplotlib

        old = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        retained = old.get("retained_clair") or {
            "note": "The Clair edition is kept as first rendered. It was drawn with six "
            "Inter faces, including italics, and this renderer no longer draws it.",
            "typography": old["typography"],
            "files": {
                item["path"]: {"sha256": item["sha256"]}
                for item in old["editions"]["clair"].values()
            },
        }
        for name in RETAINED_CLAIR:
            if digest(ROOT / name) != retained["files"][name]["sha256"]:
                raise ValueError(f"Retained Clair edition changed: {name}")
        editions = {"clair": old["editions"]["clair"]}
        for mode in ("obscur",):
            editions[mode] = {}
            for extension in ("png", "svg"):
                path = output / f"{STEM}-{mode}.{extension}"
                item = {"path": "docs/" + path.name, "sha256": digest(path)}
                if extension == "png":
                    item.update(width=WIDTH, height=layout[mode]["height"])
                editions[mode][extension] = item
                (ROOT / item["path"]).write_bytes(path.read_bytes())
        record = {
            "schema_version": 1,
            "source": source_record(), "source_commit": REVISION, "values": values,
            "request": request_record(),
            "source_sha256_lf": {n: digest(ROOT / n, text=True) for n in INPUTS},
            "editions": editions, "retained_clair": retained, "layout": layout,
            "rendering": {
                "renderer": "tools/render_evidence_figure.py", "version": 1,
                "matplotlib": matplotlib.__version__, "backend": "Agg",
                "new_measurement": False, "series_role": "accent",
                "cap_role": "warning", "axis": [0, 112000],
                "token_revision": TOKEN_REVISION, "obscur_revision": OBSCUR_REVISION,
                "theme_roles": {
                    mode: tokens["themes"][mode.capitalize()] for mode in editions
                },
            },
            "typography": {
                "source": "Three official static Inter faces supplied by --font-dir",
                "files": evidence, "painted_faces": ["Regular", "SemiBold", "Bold"],
                "png": "Rasterized from the validated static Inter files",
                "svg": "Labels outlined from the same Inter files. The title and the "
                "description stay selectable text. The source link is an anchor with an "
                "accessible name around outlined glyphs",
                "font_binaries_distributed": False,
            },
        }
        (ROOT / MANIFEST).write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    check_outputs()
    print("Rendered both PR48 editions from retained data with validated Inter")


if __name__ == "__main__":
    main()
