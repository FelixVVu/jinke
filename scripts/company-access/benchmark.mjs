#!/usr/bin/env node
// Synthetic-only scale check against unchanged production reach polygons; no file output.
import { readFileSync } from 'node:fs';
import { ingest } from './ingest.mjs';
const count=Number(process.argv[2]||20000);
if(!Number.isInteger(count)||count<1||count>100000)throw new TypeError('Count must be 1..100000.');
const pilot=JSON.parse(readFileSync(new URL('../../tests/fixtures/company-access/pilot.json',import.meta.url)));
const areas=JSON.parse(readFileSync(new URL('../../web/public/data/reach-areas.geojson',import.meta.url)));
const template=pilot.records[0];
const records=Array.from({length:count},(_,i)=>({...template,source_record_id:`synthetic-scale-${i}`,
  company_name:`SYNTHETIC SCALE COMPANY ${i}`,company_identity:{...template.company_identity,id:`synthetic-entity-${i}`},
  address:`SYNTHETIC SCALE ADDRESS ${i}`,hub_candidates:[{...template.hub_candidates[0],id:`synthetic-building-${i}`,name:`SYNTHETIC BUILDING ${i}`}]}));
const start=performance.now();
const output=ingest({...pilot,dataset_version:'synthetic-scale-v1',records},areas);
if(output.offices.features.length!==count||output.hubs.features.length!==count)throw new Error('Scale reconciliation failed.');
console.log(JSON.stringify({synthetic_only:true,records:count,hubs:count,seconds:Number(((performance.now()-start)/1000).toFixed(3)),rss_mib:Math.round(process.memoryUsage().rss/1024/1024),inventory_sha256:output.metadata.inventory_sha256}));
