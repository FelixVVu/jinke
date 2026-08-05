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


def test_mobile_panel_is_a_collapsed_bottom_sheet_by_default():
    compact = "".join(STYLE.split())
    assert "@media(max-width:760px)" in compact
    assert ".panel{position:fixed" in compact
    assert ".panel:not(.is-expanded)" in compact
    assert ".panel:not(.is-expanded) .panel-controls" in STYLE
    assert "setSheetExpanded(!mobileQuery.matches)" in MAIN
    assert 'aria-controls="panelControls"' in MAIN


def test_summary_legend_and_journey_explanation_are_clear():
    assert "${state.limit}-minute total journey" in MAIN
    assert "reachable stations · " in MAIN
    assert (
        "Total time = transit time from 金科路 + remaining walking time."
        in MAIN
    )
    for label in [
        "Orange</strong> — 金科路 origin",
        "Green</strong> — reachable station",
        "White</strong> — boundary station",
        "Gray</strong> — outside selected time",
        "Turquoise area</strong> — reachable area",
    ]:
        assert label in MAIN


def test_station_display_search_highlight_and_clear_controls_exist():
    assert "stationDisplay: 'relevant'" in MAIN
    assert '<option value="relevant">Relevant only</option>' in MAIN
    assert '<option value="all">All stations</option>' in MAIN
    assert "stationFeatureCollection(" in MAIN
    assert "findStationMatch(" in MAIN
    assert "matchingStations(" in MAIN
    assert 'id="clearSearch"' in MAIN
    assert "map.flyTo({" in MAIN
    assert "station-highlight" in MAIN
    assert "openStationPopup(feature)" in MAIN


def test_appearance_and_about_sections_use_manifest_values():
    assert '<details id="appearance"' in MAIN
    assert '<details id="about"' in MAIN
    for control_id in ["fill", "outline", "opacity", "width", "stationSize"]:
        assert f'id="{control_id}"' in MAIN
    assert "manifest.generated_at" in MAIN
    assert "manifest.limits" in MAIN
    assert "manifest.production_data" in MAIN
    assert "manifest.geometry_union" in MAIN
    assert "ORS walking-time areas" in MAIN


def test_loading_error_and_focus_states_are_present():
    assert "Loading map data…" in MAIN
    assert "The map data could not be loaded." in MAIN
    assert 'role="status"' in MAIN
    assert ":focus-visible" in STYLE
    assert "prefers-reduced-motion" in STYLE
