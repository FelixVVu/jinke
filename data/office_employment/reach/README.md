# Office-employment reach benchmark

This workstream intersects the committed fine-control office-employment grids
with the unchanged production 10/20/30/40/50-minute polygons. It does not fit or
regenerate the office allocation model, modify the Site, or replace the existing
all-employment or GDP results.

The three restricted Pudong supports are used temporarily and are not committed.
Reacquire them outside the repository, then run:

```bash
python -c "from pathlib import Path; from employment_pipeline.sources import acquire_restricted_zone_supports; p=Path('/absolute/cache/path'); p.mkdir(parents=True, exist_ok=True); acquire_restricted_zone_supports(p)"
python scripts/run_office_employment_reach.py \
  --restricted-zone-directory /absolute/cache/path
```

Aggregate reach totals are calculated directly from the committed unsmoothed
physical-cell grids. Control attribution is rehydrated in memory and must
reproduce every committed industry cell exactly before any contribution table is
accepted. Partial cells use:

`area(cell intersection reach) / clipped cell_area_m2`

Uncertainty dimensions are reported separately and are not a confidence
interval. No file under `web/public/` is created or changed.
