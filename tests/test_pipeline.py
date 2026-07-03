from pathlib import Path
import json
from pipeline.generate import Config, classify, missing_requests, build_outputs, cache_key, cache_status, legacy_50_key

def bbox(geom):
    coords=[]
    if geom['type']=='Polygon': coords=geom['coordinates'][0]
    xs=[p[0] for p in coords]; ys=[p[1] for p in coords]
    return min(xs),min(ys),max(xs),max(ys)

def contains_bbox(outer, inner, tol=1e-9):
    a=bbox(outer); b=bbox(inner)
    return a[0] <= b[0]+tol and a[1] <= b[1]+tol and a[2]+tol >= b[2] and a[3]+tol >= b[3]

def test_limit_classification_boundary_no_zero_polygon_and_excluded():
    rows=[{"station":"A","apple":9,"lon":1,"lat":2},{"station":"B","apple":10,"lon":1,"lat":2},{"station":"C","apple":11,"lon":1,"lat":2}]
    c=classify(rows,10)
    assert [r['status'] for r in c]==["included","boundary","excluded"]
    req=missing_requests(c,Config(cache_dir=Path('/tmp/no-cache'), dry_run=True))
    assert all(r['seconds']>0 for r in req)
    assert not any(r['station']=='B' and r['limit']==10 for r in req)
    assert not any(r['station']=='C' and r['limit']==10 for r in req)

def test_outputs_have_all_limits_valid_geometry_and_monotonicity(tmp_path):
    rows=[{"station":"金科路","apple":0,"lon":121.597836,"lat":31.2064028},{"station":"B","apple":10,"lon":121.6,"lat":31.2},{"station":"C","apple":55,"lon":121.7,"lat":31.3}]
    cfg=Config(web_data_dir=tmp_path/'web', audit_dir=tmp_path/'audit', cache_dir=tmp_path/'cache', dry_run=True)
    build_outputs(rows,cfg)
    areas=json.loads((tmp_path/'web/reach-areas.geojson').read_text())
    assert [f['properties']['limit'] for f in areas['features']]==[10,20,30,40,50]
    assert all(f['geometry']['coordinates'] for f in areas['features'])
    for low, high in zip(areas['features'], areas['features'][1:]):
        assert contains_bbox(high['geometry'], low['geometry'], tol=1e-6)
    assert (tmp_path/'web/stations.geojson').exists() and (tmp_path/'web/manifest.json').exists() and (tmp_path/'audit/web-data.zip').exists()

def test_cache_key_includes_validation_fields():
    assert cache_key('A',1,2,60) != cache_key('A',1,2,120)
    assert cache_key('A',1,2,60) != cache_key('B',1,2,60)

def test_station_coordinates_valid_and_manifest_limits_agree(tmp_path):
    rows=[{"station":"金科路","apple":0,"lon":121.597836,"lat":31.2064028}]
    cfg=Config(web_data_dir=tmp_path/'web', audit_dir=tmp_path/'audit', cache_dir=tmp_path/'cache', dry_run=True)
    build_outputs(rows,cfg)
    stations=json.loads((tmp_path/'web/stations.geojson').read_text())
    manifest=json.loads((tmp_path/'web/manifest.json').read_text())
    areas=json.loads((tmp_path/'web/reach-areas.geojson').read_text())
    assert manifest['limits'] == [f['properties']['limit'] for f in areas['features']]
    for f in stations['features']:
        lon,lat=f['geometry']['coordinates']
        assert -180 <= lon <= 180 and -90 <= lat <= 90

def test_legacy_50_cache_validation_reports_accept_and_reject(tmp_path):
    rows=[{"station":"金科路","apple":0,"lon":121.597836,"lat":31.2064028}]
    cfg=Config(web_data_dir=tmp_path/'web', audit_dir=tmp_path/'audit', cache_dir=tmp_path/'cache', dry_run=True)
    cfg.cache_dir.mkdir()
    sec=50*60
    good=cfg.cache_dir/f"{legacy_50_key('金科路',121.597836,31.2064028,sec)}.geojson"
    good.write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}}]}))
    bad=cfg.cache_dir/f"{legacy_50_key('金科路',121.597836,31.2064028,40*60)}.geojson"
    bad.write_text('{bad json')
    status=cache_status(rows,cfg)
    assert status['legacy_50_cache_files_found']==2
    assert status['legacy_50_cache_files_accepted']==1
    assert status['legacy_50_cache_files_rejected']==1
    assert status['legacy_rejections'][0]['reason']
