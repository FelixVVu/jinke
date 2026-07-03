"""Colab-safe data generator for Jinke metro+walk reach areas.

Dry run is the default. Set RUN_ORS=true and provide ORS_API_KEY in Colab Secrets only.
Production Colab may install geopandas/shapely for audited dissolves; this module keeps a
standard-library path for tests and dry-run sample data without network calls.
"""
from __future__ import annotations
import csv, hashlib, json, math, os, random, time, zipfile, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
LIMITS=[10,20,30,40,50]; DATA_VERSION="jinke-reach-v2"
SHEET_CSV="https://docs.google.com/spreadsheets/d/1zgjzTXIxbgGUOkAIhFW3u7HoV529hx_QZc0advznuC8/export?format=csv&gid=0"
ORS_URL="https://api.openrouteservice.org/v2/isochrones/foot-walking"
@dataclass(frozen=True)
class Config:
    sheet_csv:str=SHEET_CSV; coords_csv:Path=Path("data/station_coordinates_416.csv"); web_data_dir:Path=Path("web/public/data"); audit_dir:Path=Path("audit_outputs"); cache_dir:Path=Path(os.environ.get("JINKE_CACHE_DIR","/content/drive/MyDrive/Jinke50min/ors_cache")); dry_run:bool=os.environ.get("RUN_ORS","").lower() not in {"1","true","yes","run_ors"}; max_calls:int=int(os.environ.get("MAX_ORS_CALLS","450")); request_interval:float=float(os.environ.get("ORS_REQUEST_INTERVAL","3.5")); test_mode:bool=os.environ.get("TEST_MODE","").lower() in {"1","true","yes"}
def rows_from_csv(path_or_url:str|Path):
    if str(path_or_url).startswith('http'):
        text=urllib.request.urlopen(str(path_or_url),timeout=30).read().decode('utf-8-sig')
    else: text=Path(path_or_url).read_text(encoding='utf-8-sig')
    return list(csv.DictReader(text.splitlines()))
def cache_key(station:str, lon:float, lat:float, seconds:int)->str:
    raw=json.dumps({"station":station,"lon":round(float(lon),7),"lat":round(float(lat),7),"seconds":int(seconds),"version":DATA_VERSION},sort_keys=True,ensure_ascii=False); return hashlib.sha256(raw.encode()).hexdigest()
def legacy_50_key(station:str, lon:float, lat:float, seconds:int)->str: return hashlib.sha256(f"{station}|{float(lon):.7f}|{float(lat):.7f}|{int(seconds)}".encode()).hexdigest()
def load_stations(cfg:Config)->list[dict[str,Any]]:
    times=rows_from_csv(Path("tests/fixtures/apple_times.csv") if cfg.test_mode else cfg.sheet_csv); coords={r['station']:r for r in rows_from_csv(cfg.coords_csv)}; out=[]
    for r in times[:8] if cfg.test_mode else times:
        c=coords.get(r['station']);
        if not c: raise ValueError(f"Missing coordinates: {r['station']}")
        out.append({"ID":r.get('ID'),"station":r['station'],"apple":float(r['apple']),"lon":float(c['lon']),"lat":float(c['lat'])})
    return out
def classify(rows:list[dict[str,Any]], limit:int)->list[dict[str,Any]]:
    out=[]
    for r in rows:
        a=float(r['apple']); nr={**r,"selected_limit":limit,"remaining_walk_minutes":max(0,limit-a),"status":"included" if a<limit else ("boundary" if a==limit else "excluded")}; out.append(nr)
    return out
def validate_geojson_cache(path:Path)->tuple[bool,str]:
    try:
      obj=json.loads(path.read_text())
      fc=obj.get('data',obj)
      if fc.get('type')!='FeatureCollection' or not fc.get('features'): return False,'not a nonempty FeatureCollection'
      geom=fc['features'][0].get('geometry')
      if not geom or geom.get('type') not in {'Polygon','MultiPolygon'}: return False,'first feature is not polygonal'
      return True,'accepted'
    except Exception as e: return False,repr(e)
def cache_status(rows:list[dict[str,Any]], cfg:Config)->dict[str,Any]:
    requests=[]; legacy_found={}; legacy_rejections=[]; accepted_legacy=set(); modern_hits=0
    for r in rows:
      for L in LIMITS:
        if float(r['apple'])<L:
          sec=int((L-float(r['apple']))*60); modern=cfg.cache_dir/f"{cache_key(r['station'],r['lon'],r['lat'],sec)}.geojson"; legacy=cfg.cache_dir/f"{legacy_50_key(r['station'],r['lon'],r['lat'],sec)}.geojson"
          if modern.exists(): modern_hits+=1; continue
          if legacy.exists():
            legacy_found[str(legacy)]=legacy
            ok,reason=validate_geojson_cache(legacy)
            if ok: accepted_legacy.add(str(legacy)); continue
            legacy_rejections.append({"file":str(legacy),"station":r['station'],"limit":L,"reason":reason})
          requests.append({"station":r['station'],"lon":r['lon'],"lat":r['lat'],"seconds":sec,"limit":L,"key":cache_key(r['station'],r['lon'],r['lat'],sec)})
    under={str(L):sum(float(r['apple'])<L for r in rows) for L in LIMITS}
    return {"stations_below_limit":under,"modern_cache_hits":modern_hits,"legacy_50_cache_files_found":len(legacy_found),"legacy_50_cache_files_accepted":len(accepted_legacy),"legacy_50_cache_files_rejected":len(legacy_rejections),"legacy_rejections":legacy_rejections,"requests":requests,"estimated_additional_calls":len(requests)}
def missing_requests(rows:list[dict[str,Any]], cfg:Config)->list[dict[str,Any]]:
    return cache_status(rows,cfg)['requests']
def request_ors(req:dict[str,Any], api_key:str)->dict[str,Any]:
    import requests
    payload={"locations":[[req['lon'],req['lat']]],"range":[req['seconds']],"range_type":"time"}
    last=None
    for attempt in range(6):
      res=requests.post(ORS_URL,headers={"Authorization":api_key,"Content-Type":"application/json"},json=payload,timeout=60)
      if res.status_code in (429,500,502,503,504): last=res; time.sleep((2**attempt)+random.random()); continue
      res.raise_for_status(); return res.json()
    last.raise_for_status(); raise RuntimeError('ORS failed')
def fill_cache(rows,cfg,api_key=None):
    cfg.cache_dir.mkdir(parents=True,exist_ok=True); status=cache_status(rows,cfg); miss=status["requests"]; report={"dry_run":cfg.dry_run,"max_calls":cfg.max_calls,"failures":[],**{k:v for k,v in status.items() if k!="requests"},"missing_requests":len(miss)}
    if cfg.dry_run: return report
    if not api_key: raise RuntimeError('RUN_ORS requested but ORS_API_KEY is absent')
    for i,req in enumerate(miss[:cfg.max_calls]):
      try:
        if i: time.sleep(cfg.request_interval)
        (cfg.cache_dir/f"{req['key']}.geojson").write_text(json.dumps({"meta":req,"data":request_ors(req,api_key)},ensure_ascii=False))
      except Exception as e: report['failures'].append({"request":req,"error":repr(e)})
    return report
def circle(lon,lat,minutes):
    rad=max(minutes,1)*0.001; pts=[]
    for i in range(48):
      a=math.tau*i/48; pts.append([lon+math.cos(a)*rad,lat+math.sin(a)*rad])
    pts.append(pts[0]); return {"type":"Polygon","coordinates":[pts]}
def cached_geometry(cfg, station, lon, lat, sec):
    for key in (cache_key(station,lon,lat,sec), legacy_50_key(station,lon,lat,sec)):
      p=cfg.cache_dir/f"{key}.geojson"
      if p.exists():
        obj=json.loads(p.read_text()); fc=obj.get('data',obj); return fc['features'][0]['geometry']
    return circle(float(lon),float(lat),sec/60)
def bbox_union(geoms):
    coords=[]
    for g in geoms:
      if g['type']=='Polygon': coords += g['coordinates'][0]
    if not coords: return {"type":"Polygon","coordinates":[[]]}
    xs=[p[0] for p in coords]; ys=[p[1] for p in coords]; return {"type":"Polygon","coordinates":[[[min(xs),min(ys)],[max(xs),min(ys)],[max(xs),max(ys)],[min(xs),max(ys)],[min(xs),min(ys)]]]}
def build_outputs(rows,cfg):
    cfg.web_data_dir.mkdir(parents=True,exist_ok=True); cfg.audit_dir.mkdir(parents=True,exist_ok=True); area_features=[]
    for L in LIMITS:
      geoms=[cached_geometry(cfg,r['station'],r['lon'],r['lat'],int((L-r['apple'])*60)) for r in rows if r['apple']<L]
      area_features.append({"type":"Feature","properties":{"limit":L,"included_stations":sum(r['apple']<L for r in rows),"boundary_stations":sum(r['apple']==L for r in rows)},"geometry":bbox_union(geoms)})
    stations=[{"type":"Feature","properties":{"station":r['station'],"apple":r['apple'],"is_jinke":r['station']=='金科路'},"geometry":{"type":"Point","coordinates":[r['lon'],r['lat']]}} for r in rows]
    manifest={"data_version":DATA_VERSION,"limits":LIMITS,"generated_at":datetime.now(timezone.utc).isoformat(),"source_sheet":cfg.sheet_csv,"ors_cache_compatible":"legacy 50-minute cache supported","multi_range_verified":False,"production_data":not cfg.dry_run}
    files={"reach-areas.geojson":{"type":"FeatureCollection","features":area_features},"stations.geojson":{"type":"FeatureCollection","features":stations},"manifest.json":manifest}
    for n,o in files.items(): (cfg.web_data_dir/n).write_text(json.dumps(o,ensure_ascii=False,separators=(',',':')))
    (cfg.audit_dir/'reach-areas-full.geojson').write_text(json.dumps(files['reach-areas.geojson'],ensure_ascii=False));
    with zipfile.ZipFile(cfg.audit_dir/'web-data.zip','w') as z:
      for n in files: z.write(cfg.web_data_dir/n,arcname=n)
    return manifest
def main():
    cfg=Config(); rows=load_stations(cfg); print(json.dumps({"request_report":fill_cache(rows,cfg,os.environ.get('ORS_API_KEY')),"manifest":build_outputs(rows,cfg)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
