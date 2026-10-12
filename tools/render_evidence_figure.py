"""Render retained PR48 work versus its cap without running the solver."""

import argparse
import hashlib
import json
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .presentation import TOKEN_REVISION, load_tokens
    from .render_composition_figure import FACES, font_files
except ImportError:
    from render_composition_figure import FACES, font_files

    from presentation import TOKEN_REVISION, load_tokens

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
WIDTH, HEIGHT, DPI = 1440, 720, 120
SVG = "http://www.w3.org/2000/svg"
DC = "http://purl.org/dc/elements/1.1/"
NS = {"s": SVG}
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
    ET.register_namespace("", SVG)
    tree = ET.parse(path)
    root = tree.getroot()
    root.set("role", "img")
    root.set("aria-labelledby", "evidence-title evidence-description")
    ET.SubElement(root, f"{{{SVG}}}title", {"id": "evidence-title"}).text = TITLE
    ET.SubElement(root, f"{{{SVG}}}desc", {"id": "evidence-description"}).text = DESCRIPTION
    group = root.find(".//s:g[@id='source-link']", NS)
    if group is None:
        raise ValueError("The visible source link is missing")
    anchor = ET.Element(f"{{{SVG}}}a", {"href": GUIDE})
    for child in list(group):
        group.remove(child)
        anchor.append(child)
    group.append(anchor)
    tree.write(path, encoding="utf-8", xml_declaration=True)


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
    fonts = {
        name: FontProperties(
            fname=str(path),
            family=["Inter", "Arial", "sans-serif"],
            weight={"Regular": 400, "SemiBold": 600, "Bold": 700}.get(name, 400),
        )
        for name, path in files.items()
    }
    with rc_context({"svg.fonttype": "none", "svg.hashsalt": "solver-pr48-evidence-v1"}):
        fig = Figure(
            figsize=(WIDTH / DPI, HEIGHT / DPI), dpi=DPI, facecolor=roles["canvas"]
        )
        labels = []

        def label(x, y, text, size=24, face="Regular", gid=None, color=None, **kwargs):
            item = fig.text(
                x, y, text, fontsize=size, fontproperties=fonts[face],
                color=color or roles["text"], va="center", gid=gid, **kwargs
            )
            labels.append(item)

        label(0.05, 0.94, TITLE, 38, "Bold")
        label(0.05, 0.82, "One cold AA / dealer A request. H17 and DAS.", 26)
        label(0.05, 0.71, "All four values. Original recommendation preserved.", 26)
        left, scale = 0.07, 0.85
        width = scale * values["entered_states"] / 112000
        cap = left + scale * values["state_cap"] / 112000
        fig.add_artist(
            Rectangle(
                (left, 0.465), width, 0.115, transform=fig.transFigure,
                facecolor=roles["accent"], gid="entered-states-bar",
            )
        )
        fig.add_artist(
            Line2D(
                (cap, cap), (0.445, 0.60), transform=fig.transFigure,
                color=roles["warning"], linewidth=2, linestyle="--",
            )
        )
        label(
            cap, 0.63, f"{values['state_cap']:,} cap", 26, "SemiBold",
            gid="state-cap-value", ha="center",
        )
        label(
            left + width / 2, 0.52, f"{values['entered_states']:,}",
            30, "Bold", gid="entered-states-value", color=roles["on_accent"],
            ha="center",
        )
        label(left, 0.405, "0", 24)
        label(0.31, 0.405, "Entered numerical states", 24)
        label(0.05, 0.30, "Reuse only terminal dealer outcomes. Other shoes can refuse.", 24)
        label(0.05, 0.185, "Work versus cap, not a timing comparison.", 24)
        label(0.05, 0.07, "Retained PR48 result. Source guide.", 24, gid="source-link")
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        bounds = [item.get_window_extent(canvas.get_renderer()) for item in labels]
        if any(b.x0 < 0 or b.y0 < 0 or b.x1 > WIDTH or b.y1 > HEIGHT for b in bounds):
            raise ValueError("A retained-evidence label extends outside the canvas")
        for extension in ("png", "svg"):
            metadata = {"Description": json.dumps(values, sort_keys=True)}
            if extension == "svg":
                metadata["Date"] = None
            path = output / f"{STEM}-{mode}.{extension}"
            fig.savefig(path, metadata=metadata)
            if extension == "svg":
                add_svg_accessibility(path)
        fig.clear()


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
    for mode, edition in record["editions"].items():
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
                if struct.unpack_from(">II", raw, 16) != (WIDTH, HEIGHT):
                    raise ValueError("PNG dimensions changed")
                if (item["width"], item["height"]) != (WIDTH, HEIGHT):
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
                svg = ET.parse(path).getroot()
                box = [float(v) for v in svg.attrib["viewBox"].split()]
                if box != [0, 0, WIDTH * 72 / DPI, HEIGHT * 72 / DPI]:
                    raise ValueError("SVG dimensions changed")
                if (
                    svg.get("width") != f"{WIDTH * 72 / DPI:g}pt"
                    or svg.get("height") != f"{HEIGHT * 72 / DPI:g}pt"
                    or svg.get("role") != "img"
                    or svg.get("aria-labelledby") != "evidence-title evidence-description"
                ):
                    raise ValueError("SVG dimensions or accessible role changed")
                if (
                    svg.find("s:title", NS).text != TITLE
                    or svg.find("s:desc", NS).text != DESCRIPTION
                    or not svg.findall(".//s:text", NS)
                    or svg.find(".//s:a", NS).get("href") != GUIDE
                    or json.loads(svg.find(f".//{{{DC}}}description").text) != values
                ):
                    raise ValueError("SVG accessible text or retained values changed")
                for gid, expected in (
                    ("entered-states-value", f"{values['entered_states']:,}"),
                    ("state-cap-value", f"{values['state_cap']:,} cap"),
                ):
                    group = svg.find(f".//s:g[@id='{gid}']", NS)
                    if group is None or "".join(group.itertext()).strip() != expected:
                        raise ValueError("Visible SVG work or cap changed")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, help="Six official static Inter TTFs")
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
        for mode in ("clair", "obscur"):
            draw(values, tokens, mode, files, output)
        import matplotlib

        editions = {}
        for mode in ("clair", "obscur"):
            editions[mode] = {}
            for extension in ("png", "svg"):
                path = output / f"{STEM}-{mode}.{extension}"
                item = {"path": "docs/" + path.name, "sha256": digest(path)}
                if extension == "png":
                    item.update(width=WIDTH, height=HEIGHT)
                editions[mode][extension] = item
                (ROOT / item["path"]).write_bytes(path.read_bytes())
        record = {
            "schema_version": 1,
            "source": source_record(), "source_commit": REVISION, "values": values,
            "request": request_record(),
            "source_sha256_lf": {n: digest(ROOT / n, text=True) for n in INPUTS},
            "editions": editions,
            "rendering": {
                "renderer": "tools/render_evidence_figure.py", "version": 1,
                "matplotlib": matplotlib.__version__, "backend": "Agg",
                "new_measurement": False, "series_role": "accent",
                "cap_role": "warning", "axis": [0, 112000],
                "token_revision": TOKEN_REVISION,
                "theme_roles": {
                    mode: tokens["themes"][mode.capitalize()] for mode in editions
                },
            },
            "typography": {
                "source": "Six official static Inter faces supplied by --font-dir",
                "files": evidence, "painted_faces": ["Regular", "SemiBold", "Bold"],
                "png": "Rasterized from the validated static Inter files",
                "svg": "Real text; visitor resolves local Inter or browser fallback",
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
