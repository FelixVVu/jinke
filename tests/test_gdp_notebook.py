import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "jinke_gdp_estimation.ipynb"


def sources(kind):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return notebook, [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == kind
    ]


def test_gdp_notebook_has_exactly_eleven_guided_stages():
    notebook, markdown = sources("markdown")
    headings = [
        line
        for cell in markdown
        for line in cell.splitlines()
        if line.startswith("## Stage ")
    ]
    assert notebook["nbformat"] == 4
    assert headings == [
        "## Stage 1 — Setup",
        "## Stage 2 — Check Earthdata Secret",
        "## Stage 3 — Download/cache JRC",
        "## Stage 4 — Download/cache NASA VNP46A4",
        "## Stage 5 — Download/cache Overture Places",
        "## Stage 6 — Load district boundaries and GDP",
        "## Stage 7 — Build 100 m proxy grid",
        "## Stage 8 — Calibrate district GDP",
        "## Stage 9 — Intersect with Jinke reach polygons",
        "## Stage 10 — Validation",
        "## Stage 11 — Export `gdp-web-data.zip`",
    ]
    _, code = sources("code")
    assert len(code) == 11
    for stage in range(1, 12):
        assert code[stage - 1].startswith(f"# STAGE {stage} —")


def test_setup_is_fresh_colab_safe_and_uses_drive_cache_tree():
    _, code = sources("code")
    setup = code[0]
    assert 'drive.mount("/content/drive")' in setup
    assert "git" in setup and "clone" in setup and "pull" in setup
    assert "requirements-gdp.txt" in setup
    assert 'Path("/content/drive/MyDrive/JinkeGDP")' in setup
    assert 'SOURCE_ROOT / "jrc"' in setup
    assert 'SOURCE_ROOT / "viirs"' in setup
    assert 'SOURCE_ROOT / "overture"' in setup
    assert 'DRIVE_ROOT / "audit_outputs"' in setup


def test_earthdata_secret_is_never_printed_or_written():
    _, code = sources("code")
    secret_cell = code[1]
    all_code = "\n".join(code)
    assert 'userdata.get("EARTHDATA_TOKEN")' in secret_cell
    assert "print(EARTHDATA_TOKEN" not in all_code
    assert "write_text(EARTHDATA_TOKEN" not in all_code
    assert "to_csv(EARTHDATA_TOKEN" not in all_code
    assert "del EARTHDATA_TOKEN" in code[3]


def test_notebook_reads_production_reaches_and_exports_only_after_validation():
    _, code = sources("code")
    assert "load_production_reach_areas" in code[8]
    assert "validate_outputs" in code[9]
    assert "export_audit_outputs" in code[10]
    assert "reach-areas.geojson" not in code[10]
    assert "vercel" not in code[10].lower()
    assert "gh-pages" not in code[10].lower()


def test_new_pipeline_has_no_prohibited_network_endpoint():
    paths = list((ROOT / "gdp_pipeline").glob("*.py")) + [NOTEBOOK]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "https://api.openrouteservice" not in combined
    assert "https://restapi.amap.com" not in combined
    assert "lbs.amap.com" not in combined
