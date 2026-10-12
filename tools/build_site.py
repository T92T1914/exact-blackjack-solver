"""Build a public site from an explicit list of public example files."""

from pathlib import Path
import json
import re
import shutil
import sys

try:
    from .presentation import appearance_css
    from .render_joint_report import render_outputs
    from .render_composition_figure import check_outputs
except ImportError:
    from presentation import appearance_css
    from render_joint_report import render_outputs
    from render_composition_figure import check_outputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "_site"
FILES = {
    "site/share-preview.png": "share-preview.png",
    "docs/blackjack-composition-clair-wide.png": "composition-clair-wide.png",
    "docs/blackjack-composition-clair-wide.svg": "composition-clair-wide.svg",
    "docs/blackjack-composition-obscur-wide.png": "composition-obscur-wide.png",
    "docs/blackjack-composition-obscur-wide.svg": "composition-obscur-wide.svg",
    "site/index.html": "index.html",
    "site/style.css": "style.css",
    "site/app.js": "app.js",
    "site/record-inspection.mjs": "record-inspection.mjs",
    "site/record-inspector-ui.mjs": "record-inspector-ui.mjs",
    "site/selection-state.mjs": "selection-state.mjs",
    "site/appearance.js": "appearance.js",
    "examples/bounded-resplit-request.json": "bounded-resplit-request.json",
    "docs/bounded-resplit-calculation.md": "bounded-resplit-calculation.md",
    "examples/bounded-ace-resplit-request.json": "bounded-ace-resplit-request.json",
    "examples/bounded-ace-resplit-mixed-request.json": "bounded-ace-resplit-mixed-request.json",
    "examples/bounded-ace-resplit-h17-request.json":
        "bounded-ace-resplit-h17-request.json",
    "docs/bounded-ace-resplit-calculation.md": "bounded-ace-resplit-calculation.md",
    "docs/ace-terminal-reuse.md": "ace-terminal-reuse.md",
    "docs/ace-resplit-dealer-computation.md": "ace-resplit-dealer-computation.md",
    "docs/ace-resplit-dealer-protocol.json": "ace-resplit-dealer-protocol.json",
    "docs/ace-resplit-dealer-results.json": "ace-resplit-dealer-results.json",
    "examples/deferred-second-card-request.json": "deferred-second-card-request.json",
    "docs/deferred-second-card-calculation.md": "deferred-second-card-calculation.md",
    "docs/protected-replay.md": "protected-replay.md",
    "examples/common-shoe-mixed-request.json": "common-shoe-mixed-request.json",
    "docs/common-shoe-calculation.md": "common-shoe-calculation.md",
    "docs/common-shoe-dealer-computation.md": "common-shoe-dealer-computation.md",
    "docs/common-shoe-dealer-protocol.json": "common-shoe-dealer-protocol.json",
    "docs/common-shoe-dealer-results.json": "common-shoe-dealer-results.json",
    "docs/local-calculation.md": "local-calculation.md",
    "docs/visual-example-data.json": "data.json",
    "docs/blackjack-composition-example.svg": "example.svg",
    "docs/blackjack-composition-clair.png": "composition-clair.png",
    "docs/blackjack-composition-obscur.png": "composition-obscur.png",
    "docs/blackjack-composition-clair.svg": "composition-clair.svg",
    "docs/blackjack-composition-obscur.svg": "composition-obscur.svg",
    "docs/blackjack-composition-figure.json": "composition-figure.json",
}


def public_guide(source: str, text: str) -> str:
    """Keep source-relative guides usable after their flat Pages copy."""
    def link(match):
        target = match.group(2)
        if '://' in target or target.startswith('#'):
            return match.group(0)
        relative, separator, fragment = target.partition('#')
        resolved = ((ROOT / source).parent / relative).resolve()
        repo_path = resolved.relative_to(ROOT).as_posix()
        if not resolved.is_file():
            raise ValueError('Missing guide target: ' + repo_path)
        public = FILES.get(repo_path)
        if public is None:
            public = 'https://github.com/T92T1914/exact-blackjack-solver/blob/main/' + repo_path
        return '[' + match.group(1) + '](' + public + separator + fragment + ')'

    return re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', link, text)


def main():
    from tools.render_share_preview import check as check_share_preview

    check_share_preview()
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
        if path.suffix == '.md':
            (OUT / target).write_text(public_guide(source, path.read_text(encoding='utf-8')),
                                      encoding='utf-8', newline='\n')
        else:
            shutil.copyfile(path, OUT / target)
    (OUT / "appearance.css").write_text(css, encoding="utf-8", newline="\n")
    for target, content in report.items():
        (OUT / target).write_bytes(content)
    print("Built", len(expected), "public files in", OUT)


if __name__ == "__main__":
    main()
