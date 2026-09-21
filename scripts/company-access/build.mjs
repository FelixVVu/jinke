#!/usr/bin/env node
import { readFile, writeFile, mkdir, realpath, stat, rename, rm, mkdtemp } from 'node:fs/promises';
import { resolve, dirname, relative, isAbsolute, join, basename } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { artifactNames, ingest } from './ingest.mjs';
import { validateEnvelope } from './validate.mjs';
import { sha256, stable, compare, fail } from './common.mjs';
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const isWithin=(path,root)=>{const rel=relative(root,path);return rel===''||(!rel.startsWith('..')&&!isAbsolute(rel));};

async function resolvedTarget(path){
  try{return await realpath(path);}catch(error){
    if(error.code!=='ENOENT')throw error;
    const parent=dirname(path);if(parent===path)throw error;
    return join(await resolvedTarget(parent),basename(path));
  }
}
export async function buildFiles({inputs,output,reach=join(repo,'web/public/data/reach-areas.geojson'),settings={}}){
  if(!Array.isArray(inputs)||!inputs.length||!output)fail('MISSING_PATH_ARGUMENT');
  const target=await resolvedTarget(resolve(output));
  // A build must never write to a tracked application/model directory, including via symlinks.
  const allowedRepoRoot=join(repo,'offline-output/company-access');
  const realRepo=await realpath(repo);
  if(isWithin(target,realRepo)&&(!isWithin(target,allowedRepoRoot)||target===allowedRepoRoot))fail('UNSAFE_OUTPUT_DIRECTORY','Use a fresh run directory under offline-output/company-access or outside the repository.');
  const protectedDirectories=['web','dist','data','pipeline','office_employment_pipeline','employment_pipeline','gdp_pipeline'];
  for(const name of protectedDirectories){
    const protectedPath=await resolvedTarget(join(repo,name));
    if(isWithin(target,protectedPath))fail('UNSAFE_OUTPUT_DIRECTORY');
  }
  try{await stat(target);fail('OUTPUT_ALREADY_EXISTS');}catch(error){if(error.code!=='ENOENT')throw error;}
  const loaded=[];
  for(const file of inputs){
    const path=await realpath(resolve(file)),bytes=await readFile(path);
    loaded.push({path,bytes,input:validateEnvelope(JSON.parse(bytes.toString('utf8')))});
    if(isWithin(path,target))fail('OUTPUT_OVERLAPS_INPUT');
  }
  if(new Set(loaded.map(f=>f.path)).size!==loaded.length)fail('DUPLICATE_INPUT_FILE');
  if(new Set(loaded.map(f=>f.input.dataset_kind)).size!==1||new Set(loaded.map(f=>f.input.dataset_version)).size!==1)fail('MIXED_DATASET_ENVELOPES');
  const reachBytes=await readFile(reach),areas=JSON.parse(reachBytes.toString('utf8'));
  const input={...loaded[0].input,records:loaded.flatMap(f=>f.input.records)};
  const inputFiles=loaded.map(f=>({name:basename(f.path),sha256:sha256(f.bytes)})).sort((a,b)=>compare(stable(a),stable(b)));
  const artifacts=ingest(input,areas,{settings,reachBytes,inputFiles});
  await mkdir(dirname(target),{recursive:true});
  const staging=await mkdtemp(join(dirname(target),'.company-access-'));
  try{
    await mkdir(join(staging,'frontend'));
    await mkdir(join(staging,'audit'));
    for(const [key,name] of Object.entries(artifactNames)){
      const folder=['audit','rejected','review'].includes(key)?'audit':'frontend';
      await writeFile(join(staging,folder,name),stable(artifacts[key])+'\n',{flag:'wx'});
    }
    // No automatic publication, copy-to-web, or existing output replacement.
    try{await stat(target);fail('OUTPUT_ALREADY_EXISTS');}catch(error){if(error.code!=='ENOENT')throw error;}
    await rename(staging,target);
  }catch(error){await rm(staging,{recursive:true,force:true});throw error;}
  return {output:target,dataset_kind:input.dataset_kind,...artifacts.metadata.ingestion.dispositions};
}

export async function main(args){
  const options={inputs:[]};
  for(let i=0;i<args.length;i++){
    const flag=args[i],value=args[++i];
    if(!value||value.startsWith('--'))fail('INVALID_ARGUMENT',flag);
    if(flag==='--input')options.inputs.push(value);
    else if(flag==='--output')options.output=value;
    else if(flag==='--reach')options.reach=value;
    else if(flag==='--settings')options.settings=JSON.parse(await readFile(value,'utf8'));
    else fail('UNKNOWN_ARGUMENT',flag);
  }
  return buildFiles(options);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  main(process.argv.slice(2)).then(result=>console.log(stable(result))).catch(error=>{
    console.error(stable({error:error.code||'BUILD_FAILED',message:error.message}));process.exitCode=1;
  });
}
