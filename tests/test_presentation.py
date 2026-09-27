"""Presentation checks use retained evidence, without recalculating a hand."""

import hashlib
import json
from pathlib import Path

import pytest

from tools import build_site, presentation

ROOT = Path(__file__).resolve().parents[1]


def test_palette_is_the_reviewed_upstream_snapshot():
    raw = (ROOT / "presentation/tokens.json").read_text(encoding="utf-8").encode()
    assert hashlib.sha256(raw).hexdigest() == presentation.TOKEN_SHA256
    assert set(presentation.load_tokens()["themes"]) == {"Clair", "Obscur"}


def test_css_has_six_local_faces_and_explicit_auto_and_print_paths():
    css = presentation.appearance_css()
    assert css.count("@font-face") == 6
    assert "url(" not in css
    for _, _, full, postscript in presentation.FACES:
        assert f'local("{full}")' in css
        assert f'local("{postscript}")' in css
    assert "@media(prefers-color-scheme:dark)" in css
    assert ':root[data-appearance="clair"]' in css
    assert ':root[data-appearance="obscur"]' in css
    assert "@media print" in css


def test_build_preserves_retained_evidence_and_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "OUT", tmp_path)
    build_site.main()
    assert {p.name for p in tmp_path.iterdir()} == set(build_site.FILES.values()) | {
        "appearance.css"
    }
    for source, target in build_site.FILES.items():
        assert (tmp_path / target).read_bytes() == (ROOT / source).read_bytes()
    assert (tmp_path / "appearance.css").read_text() == presentation.appearance_css()
    data = json.loads((tmp_path / "data.json").read_text())
    assert data["source_commit"] == "23a42e6"
    assert [hand["action"] for hand in data["hands"]] == ["H", "S"]
    assert all(value < 0 for hand in data["hands"] for value in hand["values"].values())
    assert "original wager" in data["units"]


def test_unexpected_output_fails_before_touching_existing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "OUT", tmp_path)
    (tmp_path / "index.html").write_text("keep")
    (tmp_path / "unreviewed.txt").write_text("keep too")
    with pytest.raises(ValueError, match="Unexpected site output"):
        build_site.main()
    assert (tmp_path / "index.html").read_text() == "keep"


def test_changed_tokens_fail_visibly(tmp_path, monkeypatch):
    (tmp_path / "presentation").mkdir()
    (tmp_path / "presentation/tokens.json").write_text('{"themes":{}}')
    monkeypatch.setattr(presentation, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Pinned Clair/Obscur tokens changed"):
        presentation.appearance_css()
