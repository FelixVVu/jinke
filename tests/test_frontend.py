from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "web" / "src" / "main.js").read_text(encoding="utf-8")
UTILS = (ROOT / "web" / "src" / "map-utils.js").read_text(encoding="utf-8")
STYLE = (ROOT / "web" / "src" / "style.css").read_text(encoding="utf-8")


def test_basemap_switching_uses_style_load_and_no_source_r_assumption():
    assert "style.load" in UTILS
    assert "styledata" not in MAIN + UTILS
    assert "sources.r" not in MAIN
    assert "styles[state.basemap].sources.r" not in MAIN
    assert "map.once(" not in MAIN


def test_pastel_is_keyless_carto_voyager_with_correct_attribution():
    assert "rastertiles/voyager" in MAIN
    assert "carto-voyager" in MAIN
    assert "OpenStreetMap contributors © CARTO — Voyager" in MAIN
    assert "stadiamaps.com" not in MAIN


def test_inverse_checkbox_is_immediately_after_show_polygon_and_persisted():
    show_polygon = (
        '<label class="toggle"><input id="showPoly" type="checkbox"/> '
        'Show polygon</label>'
    )
    inverse = (
        '<label class="toggle"><input id="invertFill" type="checkbox"/> '
        'Invert fill — Shanghai only</label>'
    )
    assert show_polygon in MAIN
    assert inverse in MAIN
    assert MAIN.index(show_polygon) < MAIN.index(inverse)
    assert "invertFill: false" in MAIN
    assert "jinkeAppearance" in MAIN
    assert "outside-reach-areas.geojson" in MAIN


def test_existing_mobile_panel_layout_is_preserved():
    compact = STYLE.replace(" ", "")
    assert "@media(max-width:760px)" in compact
    assert ".panel{position:fixed" in compact
    assert "max-height:48%" in compact
