# Jinke Road 50-minute Metro + Walk Isochrone

This repository is designed for **GitHub + Google Colab + Google Sheet**.

## Files

- `jinke_50min_google_sheet_colab.ipynb` — the runnable Colab notebook.
- `data/station_coordinates_416.csv` — transparent copy of the 416 WGS84 station coordinates.

## Data source

The notebook reads the latest Apple Maps transit times from:

`https://docs.google.com/spreadsheets/d/1zgjzTXIxbgGUOkAIhFW3u7HoV529hx_QZc0advznuC8/edit?gid=0#gid=0`

Required columns:

- `ID`
- `station`
- `apple`

The Sheet must be viewable without sign-in for the direct CSV export URL to work in Colab.

## First run

1. Create a GitHub repository.
2. Upload the notebook and the `data` folder.
3. Open the notebook in Google Colab.
4. In Colab Secrets, add `ORS_API_KEY` and enable notebook access.
5. Run all cells with `TEST_MODE = True`.
6. Inspect the five test polygons.
7. Change `TEST_MODE = False`.
8. Rerun configuration, data-loading, coordinate-loading, ORS, union, and map cells.

## Persistent outputs

The notebook mounts Google Drive and saves outputs under:

`MyDrive/Jinke50min/`

This includes the ORS cache, so a disconnected Colab session can continue later.

## Important security note

Do not commit an ORS API key into GitHub. The old notebook contained a hard-coded key; revoke that key and use a new key through Colab Secrets.