import {createSession,validateBundle,validateSession,decide,exportRows,rowsToCSV,suggest} from './review-state.js';
const $=id=>document.getElementById(id),text=(tag,value)=>{const e=document.createElement(tag);e.textContent=value;return e;};
let bundle,session,items=[],visible=[],active=null,checked=new Set(),map,ready=false,page=0;
const draftKey=()=>`jinke-company-review:${bundle.bundle_id}`;
function status(message){$('saveStatus').textContent=message;}
function save(){try{localStorage.setItem(draftKey(),JSON.stringify(session));status('Draft saved locally. Export decisions & history before leaving / changing browser.');}catch{status('Browser storage unavailable. Export your session now to preserve decisions.');}}
function download(name,value,type='application/json'){const url=URL.createObjectURL(new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function load(value){
  validateBundle(value);bundle=value;session=createSession(bundle);checked.clear();active=null;
  // Recompute suggestions; imported suggestions can never become decisions.
  items=bundle.batches.flatMap(b=>b.rows.map(i=>({...i,batch:b.id,suggestion:['PRIOR_SOURCE_CHANGED','PRIOR_INVENTORY_MATCH'].includes(i.suggestion?.reason)?{...i.suggestion,disposition:'needs_review'}:suggest(i.row)})));
  try{const saved=localStorage.getItem(draftKey());if(saved)session=validateSession(bundle,JSON.parse(saved));}catch{status('Stored draft failed validation; unchanged source decisions loaded.');}
  $('reviewer').value=session.reviewer;$('queue').value='new';$('reason').replaceChildren(new Option('All reasons',''),...[...new Set(items.map(i=>i.suggestion.reason))].sort().map(r=>new Option(r,r)));
  render();
}
function render(){
  if(!bundle)return;const q=$('search').value.normalize('NFKC').toLowerCase().trim(),queue=$('queue').value;
  visible=items.filter(i=>(queue==='all'||(queue==='new'?!i.locked:session.decisions[i.key].status===queue))&&(!$('suggestion').value||i.suggestion.disposition===$('suggestion').value)&&(!$('reason').value||i.suggestion.reason===$('reason').value)&&[i.row.company_name,i.row.address,i.row.district,i.row.amap_poi_id].join(' ').normalize('NFKC').toLowerCase().includes(q));
  // Bulk actions are scoped to current results, never stale hidden selections.
  const visibleKeys=new Set(visible.map(i=>i.key));checked=new Set([...checked].filter(k=>visibleKeys.has(k)));
  if(!visible.some(i=>i.key===active)){active=visible[0]?.key||null;$('notes').value=active?session.decisions[active].notes:'';}
  $('status').textContent=`${visible.length} results · ${items.filter(i=>!i.locked).length} new candidates · ${items.filter(i=>i.locked).length} locked prior decisions · ${checked.size} selected`;
  const list=$('list');list.replaceChildren();
  if(!visible.length)list.append(text('p','No new candidates in this batch. Choose “All / locked history” to inspect prior reviews, or open a prepared new batch.'));
  page=Math.min(page,Math.max(0,Math.ceil(visible.length/100)-1));
  if(visible.length>100){const nav=text('div',`Page ${page+1} / ${Math.ceil(visible.length/100)} `);for(const [label,step] of [['Previous',-1],['Next',1]]){const b=text('button',label);b.disabled=step<0?page===0:(page+1)*100>=visible.length;b.onclick=()=>{page+=step;render();};nav.append(b);}list.append(nav);}
  for(const i of visible.slice(page*100,(page+1)*100)){const row=text('div','');row.className=`candidate${active===i.key?' active':''}`;
    const check=document.createElement('input');check.type='checkbox';check.disabled=i.locked;check.checked=checked.has(i.key);check.setAttribute('aria-label',`Select ${i.row.company_name}`);check.onchange=()=>{check.checked?checked.add(i.key):checked.delete(i.key);render();};
    const button=document.createElement('button');button.append(text('strong',i.row.company_name),text('small',`${i.locked?'🔒 ':''}${session.decisions[i.key].status} · ${i.row.district}`),text('small',`Suggestion: ${i.suggestion.disposition} · ${i.suggestion.reason}`));button.onclick=()=>select(i.key);row.append(check,button);list.append(row);
  }
  details();mapData();
}
function select(key){active=key;page=Math.max(0,Math.floor(visible.findIndex(i=>i.key===key)/100));$('notes').value=session.decisions[key].notes;render();const item=items.find(i=>i.key===key);if(map&&validLocation(item))map.easeTo({center:[+item.row.longitude_wgs84,+item.row.latitude_wgs84],zoom:Math.max(map.getZoom(),15)});}
function details(){const root=$('details');root.replaceChildren();const i=items.find(i=>i.key===active);if(!i){root.append(text('h2','Select a candidate'));return;}
  root.append(text('h2',i.row.company_name),text('p',i.locked?'Locked historical decision — cannot be changed in a new batch.':'Human decision required; suggestions do not affect approval.'));
  const dl=document.createElement('dl');for(const [label,value] of Object.entries({Address:i.row.address,District:i.row.district,'Provider type':`${i.row.amap_type} (${i.row.amap_typecode})`,'WGS84 location':`${i.row.longitude_wgs84}, ${i.row.latitude_wgs84}`,Suggestion:`${i.suggestion.disposition} · ${i.suggestion.reason}`,'Duplicate / conflict':`${i.row.possible_duplicate||false} ${i.row.duplicate_group||''}`,'Available evidence':i.evidence?.source||'Mapped POI only','Prior reviewer':i.prior_review?`${i.prior_review.reviewer} · ${i.prior_review.reviewed_at}`:'None',Decision:session.decisions[i.key].status,Notes:session.decisions[i.key].notes||'None','Confidence on acceptance':'Reviewed mapped office. No physical-office verification inferred.'}))dl.append(text('dt',label),text('dd',value));root.append(dl);
  try{const url=new URL(i.row.source_reference);if(url.protocol==='https:'&&url.hostname==='www.amap.com'){const a=text('a','Open source evidence ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';root.append(a);}}catch{}
  for(const button of document.querySelectorAll('[data-decision],#saveNote'))button.disabled=checked.size===0&&i.locked;
}
function validLocation(i){return i&&Number.isFinite(+i.row.longitude_wgs84)&&Number.isFinite(+i.row.latitude_wgs84)&&Math.abs(+i.row.longitude_wgs84)<=180&&Math.abs(+i.row.latitude_wgs84)<=90;}
function mapData(){if(!ready)return;map.getSource('candidates').setData({type:'FeatureCollection',features:visible.filter(validLocation).map(i=>({type:'Feature',geometry:{type:'Point',coordinates:[+i.row.longitude_wgs84,+i.row.latitude_wgs84]},properties:{key:i.key,status:session.decisions[i.key].status,selected:i.key===active}}))});}
function decision(value){try{session.reviewer=$('reviewer').value.trim();session=decide(bundle,session,checked.size?[...checked]:[active],value,$('notes').value);save();render();}catch(e){status(e.message);}}
for(const id of ['search','queue','suggestion','reason'])$(id).addEventListener('input',()=>{page=0;render();});
$('reviewer').onchange=()=>{session.reviewer=$('reviewer').value.trim();save();};
$('selectVisible').onclick=()=>{checked=new Set(visible.filter(i=>!i.locked).map(i=>i.key));render();};$('clearSelection').onclick=()=>{checked.clear();render();};
for(const button of document.querySelectorAll('[data-decision]'))button.onclick=()=>decision(button.dataset.decision);
$('saveNote').onclick=()=>{if(checked.size){status('Save notes one candidate at a time, or include a note with a bulk decision.');return;}if(active)decision(session.decisions[active].status);};
$('exportSession').onclick=()=>{validateSession(bundle,session);download(`company-review-session-${bundle.bundle_id.slice(0,12)}.json`,session);};
$('exportCSV').onclick=()=>{for(const b of bundle.batches)download(`amap-office-review-${b.id.slice(0,12)}.csv`,rowsToCSV(exportRows(bundle,session,b.id),b.columns),'text/csv;charset=utf-8');};
async function readFile(event){const file=event.target.files[0];if(!file)return null;if(file.size>20*1024*1024)throw Error('Bundle exceeds 20 MB');return JSON.parse(await file.text());}
$('openBundle').onchange=async e=>{try{const value=await readFile(e);if(value){if(bundle)download(`company-review-session-${bundle.bundle_id.slice(0,12)}.json`,session);load(value);}}catch(error){status(error.message);}};
$('restoreSession').onchange=async e=>{try{const value=await readFile(e);if(value){session=validateSession(bundle,value);$('reviewer').value=session.reviewer;save();render();}}catch(error){status(error.message);}};
document.addEventListener('keydown',e=>{if(e.ctrlKey||e.metaKey||e.altKey||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName))return;const key=e.key.toLowerCase(),index=visible.findIndex(i=>i.key===active);if(key==='j'||key==='k'){e.preventDefault();const next=visible[Math.max(0,Math.min(visible.length-1,index+(key==='j'?1:-1)))];if(next)select(next.key);}else if(['a','r','n'].includes(key)){e.preventDefault();decision({a:'accept',r:'reject',n:'needs_review'}[key]);}else if(key===' '&&active&&!items.find(i=>i.key===active).locked){e.preventDefault();checked.has(active)?checked.delete(active):checked.add(active);render();}});
try{const response=await fetch('data/company-access-review/review-bundle.json');if(!response.ok)throw Error('Review bundle unavailable');load(await response.json());
  if(globalThis.maplibregl){map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/positron',center:[121.604,31.205],zoom:12});map.on('load',()=>{map.addSource('candidates',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'candidate-points',type:'circle',source:'candidates',paint:{'circle-radius':['case',['get','selected'],10,6],'circle-color':['match',['get','status'],'accept','#285a50','reject','#888','needs_review','#b57c24','#bd3f55'],'circle-stroke-color':'#fff','circle-stroke-width':2}});ready=true;mapData();});map.on('click','candidate-points',e=>{if(e.features?.[0])select(e.features[0].properties.key);});}
  else status('Map unavailable; list review and export remain available.');
}catch(e){status(e.message);}
