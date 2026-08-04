import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "jinke_colab_generation.ipynb"
ARCHIVE = ROOT / "archive" / "jinke_50min_google_sheet_colab.ipynb"


def notebook_sources(path):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    markdown = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "markdown"
    ]
    code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    return notebook, markdown, code


def test_colab_notebook_has_five_guided_separately_runnable_stages():
    notebook, markdown, code = notebook_sources(NOTEBOOK)
    headings = [
        line
        for source in markdown
        for line in source.splitlines()
        if line.startswith("## Stage ")
    ]

    assert notebook["nbformat"] == 4
    assert headings == [
        "## Stage 1 — setup",
        "## Stage 2 — dry run",
        "## Stage 3 — five-call smoke test",
        "## Stage 4 — full lower-limit run",
        "## Stage 5 — validation and export",
    ]
    for stage in range(1, 6):
        assert any(
            f"STAGE {stage} —" in source
            for source in code
        )


def test_colab_setup_is_fresh_runtime_safe_and_creates_drive_paths():
    _, markdown, code = notebook_sources(NOTEBOOK)
    all_markdown = "\n".join(markdown)
    setup = code[0]

    assert "git" in setup and "clone" in setup and "pull" in setup
    assert "requirements.txt" in setup
    assert 'drive.mount("/content/drive")' in setup
    assert 'userdata.get("ORS_API_KEY")' in setup
    assert 'BASE_DIR / "ors_cache_50min"' in setup
    assert 'BASE_DIR / "ors_cache_multilimit_v1"' in setup
    assert "MULTILIMIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)" in setup
    assert 'BASE_DIR / "audit_outputs"' in setup
    assert "RUN_ORS = False" in setup
    assert "MAX_ORS_CALLS = 200" in setup
    assert "ORS_REQUEST_INTERVAL = 3.5" in setup

    assert "Change:" in all_markdown
    assert "Run:" in all_markdown
    assert "金科路_3000s.json" in all_markdown


def test_live_cells_default_off_and_export_cell_has_no_live_opt_in():
    _, _, code = notebook_sources(NOTEBOOK)
    smoke = next(source for source in code if "FIVE-CALL SMOKE TEST" in source)
    full = next(source for source in code if "FULL LOWER-LIMIT RUN" in source)
    export = next(
        source for source in code if "VALIDATION AND EXPORT" in source
    )

    assert "RUN_ORS = False" in smoke
    assert "MAX_ORS_CALLS = 5" in smoke
    assert "RUN_ORS = False" in full
    assert "MAX_ORS_CALLS = 200" in full
    assert "fill_cache(" not in export
    assert "assert_all_caches_complete(" in export
    assert "build_outputs(" in export
    assert "web-data.zip" in export


def test_historical_50_minute_notebook_is_restored_and_valid_json():
    notebook, markdown, code = notebook_sources(ARCHIVE)
    combined = "\n".join(markdown + code)

    assert notebook["nbformat"] == 4
    assert "ors_cache_50min" in combined
    assert "cache_path_for" in combined
    assert "TOTAL_LIMIT_MIN = 50" in combined
