import json
from pathlib import Path

from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "web" / "src" / "main.js").read_text(encoding="utf-8")
UTILS = (ROOT / "web" / "src" / "map-utils.js").read_text(encoding="utf-8")
STYLE = (ROOT / "web" / "src" / "style.css").read_text(encoding="utf-8")
LOCATION = (ROOT / "web" / "src" / "location-search.js").read_text(
    encoding="utf-8"
)
RUNTIME_CONFIG = (ROOT / "runtime-config.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


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
    assert "OpenFreeMap</a> / " in MAIN
    assert "OpenMapTiles</a> · © " in MAIN
    assert "OpenStreetMap contributors</a> (ODbL)" in MAIN
    assert MAIN.count("'fill-antialias': true") == 2


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


def test_warm_vector_basemaps_use_openfree_map_and_local_transit_data():
    assert "apple: {" in MAIN
    assert "'apple-transit': {" in MAIN
    assert "createWarmVectorStyle('apple')" in MAIN
    assert "createWarmVectorStyle('apple-transit'" in MAIN
    assert "https://tiles.openfreemap.org/planet" in UTILS
    assert "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf" in UTILS
    assert "type: 'vector'" in UTILS
    assert "shanghai-metro-lines.geojson" in MAIN
    assert "shanghai-metro-stations.geojson" in MAIN
    assert "metro-lines" in UTILS
    assert "metro-interchanges" in UTILS
    assert "metro-station-labels" in UTILS
    assert UTILS.index("warm-local-roads") < UTILS.index("id: 'metro-lines'")
    assert "restoreCustomLayers" in MAIN


def test_no_private_vendor_map_endpoints_or_official_style_claims():
    combined = (MAIN + UTILS).lower()
    for forbidden in [
        "maps.apple.com",
        "api.apple-mapkit.com",
        "cdn.apple-mapkit.com",
        "mapkitjs",
        "apple maps data",
        "official apple",
    ]:
        assert forbidden not in combined


def test_static_shanghai_metro_geojson_source_license_and_geometry():
    lines_path = (
        ROOT / "web" / "public" / "data" / "shanghai-metro-lines.geojson"
    )
    stations_path = (
        ROOT / "web" / "public" / "data" / "shanghai-metro-stations.geojson"
    )
    lines = json.loads(lines_path.read_text(encoding="utf-8"))
    stations = json.loads(stations_path.read_text(encoding="utf-8"))

    assert lines["metadata"]["source"]["license"] == "MIT"
    assert stations["metadata"]["source"]["license"] == "MIT"
    assert lines["metadata"]["source"]["retrieved_date"] == "2026-08-05"
    assert lines["metadata"]["source"]["commit"] == (
        "087310aa159d44583cc5fef240466439570dbd62"
    )
    assert len(lines["features"]) == 19
    assert {
        feature["properties"]["line_id"] for feature in lines["features"]
    } == {str(limit) for limit in range(1, 19)} | {"pujiang"}
    assert len(stations["features"]) > 400

    for feature in lines["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.geom_type in {"LineString", "MultiLineString"}
        assert geometry.is_valid
        assert not geometry.is_empty
        assert feature["properties"]["color"].startswith("#")

    for feature in stations["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.geom_type == "Point"
        assert geometry.is_valid
        assert not geometry.is_empty
        assert 120.8 < geometry.x < 122.3
        assert 30.5 < geometry.y < 32.0

    assert any(
        feature["properties"]["interchange"]
        for feature in stations["features"]
    )


def test_location_search_is_separate_and_uses_one_runtime_maptiler_key():
    assert '<label for="search">Station search</label>' in MAIN
    assert '<label for="locationSearch">Location search</label>' in MAIN
    assert MAIN.index("Station search") < MAIN.index("Location search")
    assert "window.JINKE_MAPTILER_KEY" in MAIN
    assert RUNTIME_CONFIG.strip() == "window.JINKE_MAPTILER_KEY ??= '';"
    assert "%BASE%runtime-config.js" in INDEX
    assert "api.maptiler.com/geocoding/" in LOCATION
    assert "api.maptiler.com" not in UTILS
    assert "JINKE_MAPTILER_KEY" not in UTILS
    assert "JINKE_MAPTILER_KEY = '" not in MAIN + LOCATION + RUNTIME_CONFIG


def test_location_search_has_shanghai_filters_and_no_query_persistence():
    for value in [
        "country', 'cn'",
        "bbox",
        "proximity",
        "language', 'zh,en'",
        "poi,address,street,place,locality,neighbourhood,municipality",
        "shanghai-boundary.geojson",
        "pointInGeoJson",
        "No matching place found in Shanghai.",
    ]:
        assert value in MAIN + LOCATION
    assert "locationSearch" not in MAIN[MAIN.index("function save()") : MAIN.index("const selectedAreas")]
    assert "localStorage" not in LOCATION


def test_location_search_combobox_keyboard_touch_and_mobile_ui_are_present():
    for value in [
        'role="combobox"',
        'aria-autocomplete="list"',
        'aria-controls="locationSuggestions"',
        'role="listbox"',
        'role="status"',
        "ArrowDown",
        "ArrowUp",
        "Enter",
        "Escape",
        "onmousedown",
        "onclick",
        "pointerdown",
    ]:
        assert value in MAIN
    assert ".location-suggestions" in STYLE
    assert "max-height: min(30dvh, 260px)" in STYLE
    assert "overflow-wrap: anywhere" in STYLE
    assert ".is-active" in STYLE


def test_location_marker_is_standalone_and_search_does_not_mutate_map_layers():
    assert "new maplibregl.Marker" in MAIN
    assert "SingleLocationSelection" in MAIN
    assert "locationSelection?.ensure()" in MAIN
    assert "locationSelection?.clear()" in MAIN
    assert "map.flyTo" in MAIN
    for forbidden in [
        "setStyle",
        "addSource",
        "addLayer",
        "setPaintProperty",
        "setLayoutProperty",
        "localStorage",
    ]:
        assert forbidden not in LOCATION


def test_location_failure_is_isolated_from_core_map_data_loading():
    assert "initializeLocationSearch();\n\nPromise.all([" in MAIN
    assert "fetchJson('shanghai-boundary.geojson')" in MAIN
    core_load = MAIN[MAIN.index("Promise.all([") :]
    assert "shanghai-boundary.geojson" not in core_load
    assert "rate-limited" in MAIN
    assert "invalid response" in MAIN
    assert "boundary could not be loaded" in MAIN
