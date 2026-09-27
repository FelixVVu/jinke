// Offline aggregate diagnostics. No credential access or provider calls.
import fs from 'node:fs/promises';
import {prepareReachAreas} from '../../../web/src/company-access/model.js';
import {wgs84ToGcj02} from '../../../web/src/location-search.js';
import {normalizeCoordinates} from '../coordinates.mjs';
import {validateSnapshot,candidatesFromCache} from './acquire.mjs';
import {planQueries} from './plan.mjs';
export function diagnoseCoverage({snapshot,areas,offices,station}){
  validateSnapshot(snapshot,areas);const reach=prepareReachAreas(areas),prepared=candidatesFromCache(snapshot,areas);
  const raw=snapshot.responses.flatMap(r=>r.payload.pois),valid=[];let maxError=0,invalid=0;
  for(const poi of raw){try{const gcj=poi.location.split(',').map(Number),wgs=normalizeCoordinates({longitude:gcj[0],latitude:gcj[1],coordinate_system:'GCJ02'}).coordinates;
    const roundtrip=wgs84ToGcj02(...wgs);maxError=Math.max(maxError,...gcj.map((v,i)=>Math.abs(v-roundtrip[i])));valid.push({poi,wgs});}catch{invalid++;}}
  const inside=(coords,n)=>reach.contains(coords,n);
  const approvedMismatch=offices.features.filter(f=>{const original=valid.find(p=>p.poi.id===JSON.parse(f.properties.source_id)[1]);return !original||Math.max(...original.wgs.map((v,i)=>Math.abs(v-f.geometry.coordinates[i])))>1e-10;}).length;
  const cells=snapshot.plan.cells.map(c=>({...c,pages:snapshot.responses.filter(r=>snapshot.plan.queries.find(q=>q.id===r.query_id)?.cell_id===c.id).length,contains_station:station[0]>=c.bbox_wgs84[0]&&station[0]<=c.bbox_wgs84[2]&&station[1]>=c.bbox_wgs84[1]&&station[1]<=c.bbox_wgs84[3]}));
  return {interpretation:'Missing inventory, not an empty reach area. Bounded coarse provider sampling cannot establish absence.',raw_pois:raw.length,invalid_coordinates:invalid,raw_inside_10:valid.filter(p=>inside(p.wgs,10)).length,provider_candidates_inside_10:prepared.candidates.filter(c=>inside([c.longitude_wgs84,c.latitude_wgs84],10)).length,approved_inside_10:offices.features.filter(f=>inside(f.geometry.coordinates,10)).length,approved_coordinate_mismatches:approvedMismatch,max_roundtrip_error_degrees:maxError,station_inside_10:inside(station,10),exclusions:Object.fromEntries([...new Set(prepared.exclusions.map(e=>e.reason))].map(k=>[k,prepared.exclusions.filter(e=>e.reason===k).length])),cells,pilot2:planQueries(areas,'amap-pilot-2')};
}
export function coverageSVG(report,areas,station){
 const box=report.cells.reduce((b,c)=>[Math.min(b[0],c.bbox_wgs84[0]),Math.min(b[1],c.bbox_wgs84[1]),Math.max(b[2],c.bbox_wgs84[2]),Math.max(b[3],c.bbox_wgs84[3])],[Infinity,Infinity,-Infinity,-Infinity]);
 const x=v=>40+(v-box[0])/(box[2]-box[0])*850,y=v=>520-(v-box[1])/(box[3]-box[1])*420;
 const rect=(b,fill,stroke)=>`<rect x="${x(b[0])}" y="${y(b[3])}" width="${x(b[2])-x(b[0])}" height="${y(b[1])-y(b[3])}" fill="${fill}" stroke="${stroke}"/>`;
 const feature=areas.features.find(f=>f.properties.limit===10),polys=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;
 return `<svg xmlns="http://www.w3.org/2000/svg" width="940" height="610" viewBox="0 0 940 610"><rect width="940" height="610" fill="#fffdfb"/><g font-family="sans-serif"><text x="40" y="36" font-size="22">Jinke Road · sampling coverage, not office density</text><text x="40" y="63" font-size="13">Pilot 1: coarse 30-minute bbox cells · numbers = pages queried · north ↑</text>${report.cells.map(c=>rect(c.bbox_wgs84,c.pages===2?'#ddd8d0':'#f0ede8','#fff')+`<text x="${x((c.bbox_wgs84[0]+c.bbox_wgs84[2])/2)}" y="${y((c.bbox_wgs84[1]+c.bbox_wgs84[3])/2)}" text-anchor="middle" font-size="15">${c.pages}</text>`).join('')}${polys.map(p=>`<path d="${p.map(r=>'M'+r.map(([a,b])=>`${x(a)},${y(b)}`).join('L')+'Z').join('')}" fill="#cb546044" stroke="#a63148" fill-rule="evenodd"/>`).join('')}${report.pilot2.cells.map(c=>rect(c.bbox_wgs84,'none','#25857e')).join('')}<circle cx="${x(station[0])}" cy="${y(station[1])}" r="5" fill="#222"/><text x="40" y="555" font-size="13">Rose: exact 10-minute reach · green: planned Pilot 2 grid · black: Jinke Road station</text><text x="40" y="580" font-size="13">All 600 returned Pilot 1 POIs fall outside 10 minutes. Zero inventory is not evidence of zero offices.</text></g></svg>`;
}
if(process.argv[1]?.endsWith('diagnose-coverage.mjs')){
 const [snapshotPath,officePath,output]=process.argv.slice(2);if(!output)throw Error('Usage: snapshot offices output-directory');
 const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));const areas=await read('web/public/data/reach-areas.geojson'),station=(await read('web/public/data/stations.geojson')).features.find(f=>f.properties.is_jinke).geometry.coordinates;
 const report=diagnoseCoverage({snapshot:await read(snapshotPath),offices:await read(officePath),areas,station});await fs.mkdir(output,{recursive:true});await fs.writeFile(output+'/coverage.json',JSON.stringify(report,null,2));await fs.writeFile(output+'/coverage.svg',coverageSVG(report,areas,station));console.log(JSON.stringify({...report,cells:undefined,pilot2:undefined}));
}
