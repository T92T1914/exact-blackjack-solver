"""Small CSS adapter for the retained Clair/Obscur theme tokens."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_REVISION = "7a57fe750ff50205a17e1d342106a0d3f2777159"
TOKEN_SHA256 = "889df65e0f4f4eea99a81c535d542e7332b537c000c332402a3ffa6a6cbb15b7"
FACES = (
    (400, "normal", "Inter Regular", "Inter-Regular"),
    (600, "normal", "Inter SemiBold", "Inter-SemiBold"),
    (700, "normal", "Inter Bold", "Inter-Bold"),
    (400, "italic", "Inter Italic", "Inter-Italic"),
    (600, "italic", "Inter SemiBold Italic", "Inter-SemiBoldItalic"),
    (700, "italic", "Inter Bold Italic", "Inter-BoldItalic"),
)


def load_tokens():
    """Normalize text line endings without accepting changed palette content."""
    raw = (ROOT / "presentation/tokens.json").read_text(encoding="utf-8")
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != TOKEN_SHA256:
        raise ValueError("Pinned Clair/Obscur tokens changed. Review the source revision.")
    return json.loads(raw)


def appearance_css():
    tokens = load_tokens()

    def declarations(theme):
        values = "".join(f"--{role}:{value};" for role, value in tokens["themes"][theme].items())
        return f"color-scheme:{'light' if theme == 'Clair' else 'dark'};" + values

    light, dark = (declarations(theme) for theme in ("Clair", "Obscur"))
    fonts = "\n".join(
        '@font-face{font-family:"Solver Inter";'
        f'src:local("{full}"),local("{postscript}");'
        f"font-weight:{weight};font-style:{style};font-display:swap}}"
        for weight, style, full, postscript in FACES
    )
    return (
        f"/* Clair/Obscur source: {TOKEN_REVISION}. Local fonts only. */\n"
        + fonts
        + f"\n:root{{{light}}}\n"
        + '@media(prefers-color-scheme:dark){:root:not([data-appearance="clair"])'
        + f"{{{dark}}}}}\n"
        + f':root[data-appearance="obscur"]{{{dark}}}\n'
        + f':root[data-appearance="clair"]{{{light}}}\n'
        + f"@media print{{:root,:root[data-appearance]{{{light}}}}}\n"
    )
