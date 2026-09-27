"""Build a public site from an explicit list of public example files."""

from pathlib import Path
import json
import shutil

try:
    from .presentation import appearance_css
    from .render_joint_report import render_outputs
    from .render_composition_figure import check_outputs
except ImportError:
    from presentation import appearance_css
    from render_joint_report import render_outputs
    from render_composition_figure import check_outputs

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
FILES = {
    "site/index.html": "index.html",
    "site/style.css": "style.css",
    "site/app.js": "app.js",
    "site/selection-state.mjs": "selection-state.mjs",
    "site/appearance.js": "appearance.js",
    "docs/visual-example-data.json": "data.json",
    "docs/blackjack-composition-example.svg": "example.svg",
    "docs/blackjack-composition-clair.png": "composition-clair.png",
    "docs/blackjack-composition-obscur.png": "composition-obscur.png",
    "docs/blackjack-composition-clair.svg": "composition-clair.svg",
    "docs/blackjack-composition-obscur.svg": "composition-obscur.svg",
    "docs/blackjack-composition-figure.json": "composition-figure.json",
}


def main():
    data = json.loads((ROOT / "docs/visual-example-data.json").read_text())
    if not data.get("source_commit"):
        raise ValueError("Example data must retain its source revision.")
    check_outputs()
    OUT.mkdir(exist_ok=True)
    css = appearance_css()
    report = render_outputs()
    expected = set(FILES.values()) | {"appearance.css"} | set(report)
    unexpected = {p.name for p in OUT.iterdir()} - expected
    if unexpected:
        raise ValueError("Unexpected site output files: " + str(sorted(unexpected)))
    for source, target in FILES.items():
        path = ROOT / source
        if not path.is_file() or path.is_symlink():
            raise ValueError("Expected a regular source file: " + source)
        shutil.copyfile(path, OUT / target)
    (OUT / "appearance.css").write_text(css, encoding="utf-8", newline="\n")
    for target, content in report.items():
        (OUT / target).write_bytes(content)
    print("Built", len(expected), "public files in", OUT)


if __name__ == "__main__":
    main()
