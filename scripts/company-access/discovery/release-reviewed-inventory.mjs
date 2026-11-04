import fs from 'node:fs/promises';import path from 'node:path';
import {validateInventory} from './import-reviewed-inventory.mjs';
import {stable,sha256} from '../common.mjs';import {artifactNames} from '../ingest.mjs';import {writeReviewBundle} from '../amap/console.mjs';
const [base,sessionFile,output]=process.argv.slice(2);
if(!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Fresh offline output required');
const r=await validateInventory(base,sessionFile),byID=new Map(r.reports.map(x=>[x.amap_poi_id,x]));
for(const d of r.decisions){const x=byID.get(d.amap_poi_id);if(x){d.validation_status=x.validation_status;d.validation_reasons=x.reason_codes;}}
await fs.mkdir(output);for(const dir of ['frontend','audit','approved'])await fs.mkdir(path.join(output,dir));
const write=(p,v)=>fs.writeFile(path.join(output,p),stable(v)+'\n',{flag:'wx'});
for(const [key,name]of Object.entries(artifactNames))await write(path.join(['audit','rejected','review'].includes(key)?'audit':'frontend',name),r.artifacts[key]);
await write('approved/raw-input.json',r.envelope);await write('audit/human-review.json',{decisions:r.decisions});await write('audit/inventory-validation-report.json',r.report);await write('audit/individual-validation.json',r.reports);await write('audit/quarantined-accepts.json',r.reports.filter(x=>x.validation_status==='quarantined'));
await fs.copyFile(sessionFile,path.join(output,'audit/human-session.json'));await fs.cp(path.join(base,'source-imports'),path.join(output,'source-imports'),{recursive:true});
await fs.cp(path.join(base,'audit'),path.join(output,'source-imports/prior-release-audit'),{recursive:true});
const digest=sha256(stable(r.session)).slice(0,16),folder=`source-imports/coverage-${digest}`;await fs.mkdir(path.join(output,folder));
const batches=structuredClone(r.combined.batches.filter(b=>b.rows.some(i=>!i.locked)));for(const b of batches){b.rows=b.rows.filter(i=>!i.locked);b.id='imported-'+b.id;for(const i of b.rows)i.key=`${b.id}:${i.row.amap_poi_id}`;}
await write(folder+'/recovery-bundle.json',{schema_version:1,bundle_id:sha256(stable(batches)),batches});
const history=await writeReviewBundle(output,path.join(output,'audit/review-history.json'));
const rows=history.batches.flatMap(b=>b.rows);if(rows.length!==r.report.historical_decisions||new Set(rows.map(i=>i.row.amap_poi_id)).size!==rows.length||rows.some(i=>!i.locked))throw Error('HISTORY_RECONCILIATION_FAILED');
// Independent dispositions remain visible without changing original choices or history.
console.log(stable(r.report));
