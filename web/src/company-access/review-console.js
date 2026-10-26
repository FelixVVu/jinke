import {createSession,validateBundle,validateSession,decide,exportRows,rowsToCSV} from './review-state.js';
import {createReviewSearchIndex} from './search.js';
import {attachReviewHistory} from './review-history.js';
import {appendPending,appendDiscovery} from './review-append.js';
import {scopeItems,resumeAppended} from './review-scope.js';
import {renderTargetedPanel} from './targeted-panel.js';
import {renderCoveragePanel,insideCoverageCell} from './coverage-panel.js';
import {GROUPS,REASONS,triageItems,validateSecondPass,sampleGroup,groupTargets,confirmGroup,isPriority} from './review-triage.js';
const $=id=>document.getElementById(id),text=(tag,value)=>{const e=document.createElement(tag);e.textContent=value;return e;};
const LABEL={pending:'尚未决定',accept:'接受',reject:'排除',needs_review:'待核实'};
let bundle,session,items=[],visible=[],active=null,checked=new Set(),map,ready=false,page=0;
let searchCandidates=()=>[],historyBundle,defaultPack,currentPack,coverageData={type:'FeatureCollection',features:[]};
let group='trusted',sampleKeys=null,priority=false,openedSamples=new Set(),confirmationGroup=null;
let selectedCell=null;
let batchScope='all',confirmationItems=[];
const scoped=()=>scopeItems(items,batchScope);
const draftKey=()=>`jinke-company-review:${bundle.bundle_id}`;
function status(message){$('saveStatus').textContent=message;}
function save(){try{localStorage.setItem(draftKey(),JSON.stringify(session));status('草稿已存于当前浏览器。完成后点「导出决定与历史」，保留一个 JSON 文件用于验证导入。');}catch{status('浏览器存储不可用，请立即导出决定与历史。');}}
function download(name,value,type='application/json'){const url=URL.createObjectURL(new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function load(value,pack=null,migrated=null,preferredBatch='all'){
  validateBundle(value);if(pack)validateSecondPass(value,pack);
  currentPack=pack;
  const nextItems=triageItems(value.batches.flatMap(b=>b.rows.map(i=>({...i,batch:b.id}))),pack?.evidence,pack?.seeds);
  // Suggestions are separate from immutable rows and never initialize decisions.
  bundle=value;session=createSession(bundle);items=nextItems;checked.clear();active=null;sampleKeys=null;priority=false;openedSamples.clear();selectedCell=null;
  if(value.coverage)coverageData=value.coverage;
  searchCandidates=createReviewSearchIndex(items);
  try{session=resumeAppended(bundle,migrated||session,localStorage.getItem(draftKey()));}catch{status('旧草稿未通过验证；原始决定已保留，未覆盖。');if(migrated)session=validateSession(bundle,migrated);}
  batchScope=preferredBatch;
  $('batchScope').replaceChildren(new Option('全部批次（含历史）','all'),...bundle.batches.filter(b=>b.rows.some(i=>!i.locked)).map(b=>new Option(`${b.label||'恢复候选'} · ${b.rows.length} 条`,b.id)));
  $('batchScope').value=batchScope;
  $('reviewer').value=session.reviewer;$('queue').value='new';$('search').value='';$('suggestion').value='';
  $('reason').replaceChildren(new Option('全部原因',''),...[...new Set(items.map(i=>i.triage.reason))].sort().map(r=>new Option(REASONS[r]||r,r)));
  group=items.some(i=>!i.locked)?'trusted':'history';if(group==='history')$('queue').value='all';
  const publicCount=items.filter(i=>!i.locked&&i.triage.public_evidence).length;
  $('triageSummary').textContent=`二次筛选：本批 ${items.filter(i=>!i.locked).length} 条，${publicCount} 条附定向公开资料查证；其余依据 POI 字段，未声称逐条外部核实。分组不是最终决定。`;
  render();
}
function clearCoverageSelection(){selectedCell=null;for(const id of ['coverageContent','targetedContent']){const select=$(id).querySelector('select');if(select)select.value='';}}
function changeGroup(next){clearCoverageSelection();if(['history','all'].includes(next)){batchScope='all';$('batchScope').value='all';}group=next;sampleKeys=null;priority=false;page=0;checked.clear();$('search').value='';$('reason').value='';$('suggestion').value='';$('queue').value=['history','all'].includes(next)?'all':'new';render();}
function renderGroups(){
  $('groups').replaceChildren();
  for(const g of ['trusted','exception','exclude','history','all']){
    const all=scoped().filter(i=>g==='all'||i.triage.group===g),pending=groupTargets(scoped(),session,g).length;
    const b=document.createElement('button');b.className=`group-card ${g}${group===g?' selected':''}`;b.setAttribute('aria-pressed',String(group===g));
    b.append(text('span',GROUPS[g]),text('strong',String(all.length)),text('small',g==='history'?'历史决定始终锁定':g==='all'?'跨分组与历史搜索':`${pending} 条尚未决定`));b.onclick=()=>changeGroup(g);$('groups').append(b);
  }
  const targets=groupTargets(scoped(),session,group),isHistory=group==='history';
  $('sampleGroup').disabled=isHistory||!targets.length;$('confirmGroup').disabled=isHistory||!targets.length;
  $('priorityOnly').disabled=group!=='exception';$('priorityOnly').textContent=priority?'显示全部例外':`只看关键例外（${scoped().filter(isPriority).length}）`;
  $('confirmGroup').textContent={trusted:'批量确认接受',exclude:'批量确认排除',exception:'整组标记待核实',history:'历史决定已锁定',all:'请先选择审核分组'}[group];
  $('scopeNotice').textContent=sampleKeys?`抽查视图：${sampleKeys.size} 条；本组批量按钮会作用于全部 ${targets.length} 条尚未决定记录。`:isHistory?'仅查看，不能修改历史决定。':`本组批量操作：${targets.length} 条尚未决定记录；已决定记录不会覆盖。`;
}
function render(){
  if(!bundle)return;const queue=$('queue').value;
  visible=scopeItems(searchCandidates($('search').value),batchScope).filter(i=>insideCoverageCell(i,selectedCell)&&(group==='all'||i.triage.group===group)&&(queue==='all'||(queue==='new'?!i.locked:session.decisions[i.key].status===queue))&&(!$('suggestion').value||i.triage.disposition===$('suggestion').value)&&(!$('reason').value||i.triage.reason===$('reason').value)&&(!sampleKeys||sampleKeys.has(i.key))&&(!priority||isPriority(i)));
  visible.sort((a,b)=>Number(isPriority(b))-Number(isPriority(a))||a.key.localeCompare(b.key));
  const visibleKeys=new Set(visible.map(i=>i.key));checked=new Set([...checked].filter(k=>visibleKeys.has(k)));
  if(!visible.some(i=>i.key===active)){active=visible[0]?.key||null;$('notes').value=active?session.decisions[active].notes:'';}
  renderGroups();
  const remaining=scoped().filter(i=>!i.locked&&session.decisions[i.key].status==='pending').length;
  $('triageSummary').textContent=`当前范围 ${scoped().filter(i=>!i.locked).length} 条候选，其中 ${scoped().filter(i=>!i.locked&&i.triage.public_evidence).length} 条附定向公开资料；其余依据 POI 字段，未声称逐条外部核实。分组不是决定。`;
  $('status').textContent=`${selectedCell?`区域 ${selectedCell.properties.cell_id} · `:''}${visible.length} 条可见 · 本批尚未决定 ${remaining} 条 · ${items.filter(i=>i.locked).length} 条历史锁定 · 已勾选 ${checked.size} 条`;
  const list=$('list');list.replaceChildren();
  if(!visible.length)list.append(text('p','当前分组与筛选没有匹配记录。搜索历史公司请先选择「历史锁定」。'));
  page=Math.min(page,Math.max(0,Math.ceil(visible.length/100)-1));
  if(visible.length>100){const nav=text('div',`${page+1} / ${Math.ceil(visible.length/100)} 页 `);for(const [label,step]of [['上一页',-1],['下一页',1]]){const b=text('button',label);b.disabled=step<0?page===0:(page+1)*100>=visible.length;b.onclick=()=>{page+=step;render();};nav.append(b);}list.append(nav);}
  for(const i of visible.slice(page*100,(page+1)*100)){
    const row=text('div','');row.className=`candidate${active===i.key?' active':''}`;
    const check=document.createElement('input');check.type='checkbox';check.disabled=i.locked;check.checked=checked.has(i.key);check.setAttribute('aria-label',`勾选 ${i.row.company_name}`);check.onchange=()=>{check.checked?checked.add(i.key):checked.delete(i.key);render();};
    const button=document.createElement('button');button.append(text('strong',i.row.company_name),text('small',`${i.locked?'🔒 ':''}${LABEL[session.decisions[i.key].status]} · ${i.row.district}`),text('small',i.triage.explanation));
    if(i.triage.public_evidence)button.append(text('span',i.triage.tier==='public_address'?'公开地址佐证':'附公开资料'));button.onclick=()=>select(i.key);row.append(check,button);list.append(row);
  }
  details();mapData();
}
function select(key){active=key;if(sampleKeys?.has(key))openedSamples.add(key);page=Math.max(0,Math.floor(visible.findIndex(i=>i.key===key)/100));$('notes').value=session.decisions[key].notes;render();const item=items.find(i=>i.key===key);if(map&&validLocation(item))map.easeTo({center:[+item.row.longitude_wgs84,+item.row.latitude_wgs84],zoom:Math.max(map.getZoom(),15)});}
function evidenceLink(root,label,value){try{const url=new URL(value);if(url.protocol!=='https:'||url.username||url.password)return;const a=text('a',label+' ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';root.append(a);}catch{}}
function details(){
  const root=$('details');root.replaceChildren();const i=items.find(i=>i.key===active);
  for(const button of document.querySelectorAll('[data-decision],#saveNote'))button.disabled=!i||(checked.size===0&&i.locked);
  if(!i){root.append(text('h2','选择候选'));return;}
  root.append(text('p',GROUPS[i.triage.group]),text('h2',i.row.company_name),text('p',i.triage.explanation));
  const e=i.triage.public_evidence,card=text('section','');card.className='evidence-card';
  card.append(text('h3',e?'公开资料与判断范围':'证据范围：AMap POI'),text('p',e?e.summary:'本条未逐条核实外部公开资料。名称、地址和类别的一致性只能形成审核建议。'));
  if(e){card.append(text('p',e.limitations));for(const s of e.sources)evidenceLink(card,`${s.title} · 查阅 ${s.checked_at}`,s.url);}
  if(i.triage.seed_flags.length)card.append(text('small',`附件原始标记：${i.triage.seed_flags.join(' / ')}（仅供审计，未当作人工决定）`));root.append(card);
  if(i.evidence?.recovery)root.append(text('p',`发现链：原缓存恢复 · ${i.evidence.recovery.original_exclusions.join(' / ')}。原查询和快照指纹保留在离线审计中。`));
  if(i.evidence?.discovery){root.append(text('p','定向发现：公开资料仅提供名称／地址线索，尚未绑定实体身份或验证在驻。'));for(const s of i.evidence.sources||[])evidenceLink(root,s.title,s.url);}
  const dl=document.createElement('dl');
  for(const [label,value]of Object.entries({'地址':i.row.address,'地区':i.row.district,'POI 类别':`${i.row.amap_type} (${i.row.amap_typecode})`,'WGS84 坐标':`${i.row.longitude_wgs84}, ${i.row.latitude_wgs84}`,'来源 ID':i.row.amap_poi_id,'二次筛选原因':i.triage.reason,'重复／冲突标记':`${i.row.possible_duplicate||false} ${i.row.duplicate_group||''}`,'原始自动建议（未采纳为决定）':`${i.suggestion?.disposition||'—'} · ${i.suggestion?.reason||'—'}`,'历史审核人':i.prior_review?`${i.prior_review.reviewer} · ${i.prior_review.reviewed_at}`:'无','当前决定':LABEL[session.decisions[i.key].status],'置信级别':'接受仍为 reviewed mapped office；不会自动升级为 verified physical office。'}))dl.append(text('dt',label),text('dd',value));root.append(dl);
  if(i.locked)root.append(text('p','历史决定已锁定，新建议不能覆盖。'));
  evidenceLink(root,'查看 AMap 原始来源',i.row.source_reference);
}
function validLocation(i){return i&&Number.isFinite(+i.row.longitude_wgs84)&&Number.isFinite(+i.row.latitude_wgs84)&&Math.abs(+i.row.longitude_wgs84)<=180&&Math.abs(+i.row.latitude_wgs84)<=90;}
function mapData(){if(!ready)return;
  if(!map.getSource('pilot3-coverage')){map.addSource('pilot3-coverage',{type:'geojson',data:coverageData});map.addLayer({id:'pilot3-cells',type:'fill',source:'pilot3-coverage',paint:{'fill-color':['match',['get','status'],'failed_incomplete','#bb5362','saturated_incomplete','#d49b35','sampled_partial','#23856f','#849097'],'fill-opacity':.16}},'candidate-points');map.addLayer({id:'pilot3-cell-outlines',type:'line',source:'pilot3-coverage',paint:{'line-color':'#9a8067','line-width':.7}},'candidate-points');}
  map.getSource('pilot3-coverage').setData(coverageData);map.getSource('candidates').setData({type:'FeatureCollection',features:visible.filter(validLocation).map(i=>({type:'Feature',geometry:{type:'Point',coordinates:[+i.row.longitude_wgs84,+i.row.latitude_wgs84]},properties:{key:i.key,status:session.decisions[i.key].status,selected:i.key===active}}))});
}
function decision(value){try{session.reviewer=$('reviewer').value.trim();session=decide(bundle,session,checked.size?[...checked]:[active],value,$('notes').value);save();render();}catch(e){status(e.message);}}
for(const id of ['search','queue','suggestion','reason'])$(id).addEventListener('input',()=>{page=0;sampleKeys=null;if(id==='search'&&$('search').value.trim()){clearCoverageSelection();batchScope='all';$('batchScope').value='all';group='all';priority=false;$('queue').value='all';$('reason').value='';$('suggestion').value='';}render();});
$('batchScope').onchange=()=>{batchScope=$('batchScope').value;changeGroup('trusted');};
$('reviewer').onchange=()=>{if(session){session.reviewer=$('reviewer').value.trim();save();}};
$('selectVisible').onclick=()=>{checked=new Set(visible.filter(i=>!i.locked).map(i=>i.key));render();};$('clearSelection').onclick=()=>{checked.clear();render();};
$('sampleGroup').onclick=()=>{const samples=sampleGroup(groupTargets(scoped(),session,group));sampleKeys=new Set(samples.map(i=>i.key));$('search').value='';$('reason').value='';$('suggestion').value='';$('queue').value='new';priority=false;page=0;render();if(active)select(active);};
$('showGroup').onclick=()=>changeGroup(group);$('priorityOnly').onclick=()=>{sampleKeys=null;priority=!priority;page=0;render();};
$('confirmGroup').onclick=()=>{
  if(!$('reviewer').value.trim()){status('请先填写审核人姓名。');$('reviewer').focus();return;}
  const targets=groupTargets(scoped(),session,group);if(!targets.length)return;confirmationGroup=group;confirmationItems=[...scoped()];
  $('confirmTitle').textContent=$('confirmGroup').textContent;
  $('confirmDescription').textContent=`将对当前批次范围「${$('batchScope').selectedOptions[0].textContent}」的「${GROUPS[group]}」全部 ${targets.length} 条尚未决定记录设为「${LABEL[{trusted:'accept',exclude:'reject',exception:'needs_review'}[group]]}」。包含搜索／抽查未显示的记录；其他批次、已决定记录与历史锁定记录不受影响。`;
  $('confirmEvidence').textContent=`其中 ${targets.filter(i=>i.triage.tier==='public_address').length} 条有公开地址佐证，${targets.filter(i=>!i.triage.public_evidence).length} 条仅依据 POI。已打开本组抽查详情 ${targets.filter(i=>openedSamples.has(i.key)).length} 条；抽查不能保证全组准确。${group==='exception'?'待核实将继续排除在公司地图之外。':'此操作不发布到公司地图，仍需原有验证导入。'}`;
  $('acknowledge').checked=false;$('bulkNotes').value='';$('confirmDialog').showModal();
};
$('cancelConfirm').onclick=()=>{$('confirmDialog').close();confirmationGroup=null;};
$('confirmation').onsubmit=e=>{e.preventDefault();try{session.reviewer=$('reviewer').value.trim();session=confirmGroup(bundle,session,confirmationItems,confirmationGroup,{confirmed:$('acknowledge').checked,notes:$('bulkNotes').value});$('confirmDialog').close();confirmationGroup=null;confirmationItems=[];if(active)$('notes').value=session.decisions[active].notes;save();checked.clear();render();}catch(error){status(error.message);}};
for(const button of document.querySelectorAll('[data-decision]'))button.onclick=()=>decision(button.dataset.decision);
$('saveNote').onclick=()=>{if(checked.size){status('保存备注请只选择一条，或随批量决定一起保存。');return;}if(active)decision(session.decisions[active].status);};
$('exportSession').onclick=()=>{if(!bundle)return;validateSession(bundle,session);download(`company-review-session-${bundle.bundle_id.slice(0,12)}.json`,session);status('已导出审核决定与完整历史。请交回 JSON 进行验证导入；当前公司地图仍保留已批准数据。');};
$('exportCSV').onclick=()=>{if(bundle)for(const b of bundle.batches)download(`amap-office-review-${b.id.slice(0,12)}.csv`,rowsToCSV(exportRows(bundle,session,b.id),b.columns),'text/csv;charset=utf-8');};
async function readFile(event){const file=event.target.files[0];if(!file)return null;if(file.size>20*1024*1024)throw Error('文件超过 20 MB');return JSON.parse(await file.text());}
$('openBundle').onchange=async e=>{try{const value=await readFile(e);if(value){if(!historyBundle)throw Error('历史决定尚未加载');const next=appendDiscovery(bundle,value,historyBundle,session,currentPack);download(`company-review-session-${bundle.bundle_id.slice(0,12)}.json`,session);load(next.bundle,next.pack,next.session,value.batches[0].id);save();render();if(value.discovery_report)showTargeted(value.discovery_report);}}catch(error){status(error.message);}};
$('restoreSession').onchange=async e=>{try{const value=await readFile(e);if(value){session=validateSession(bundle,value);$('reviewer').value=session.reviewer;if(active)$('notes').value=session.decisions[active].notes;save();render();}}catch(error){status(error.message);}};
document.addEventListener('keydown',e=>{if($('confirmDialog').open||e.ctrlKey||e.metaKey||e.altKey||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName))return;const key=e.key.toLowerCase(),index=visible.findIndex(i=>i.key===active);if(key==='j'||key==='k'){e.preventDefault();const next=visible[Math.max(0,Math.min(visible.length-1,index+(key==='j'?1:-1)))];if(next)select(next.key);}else if(['a','r','n'].includes(key)){e.preventDefault();decision({a:'accept',r:'reject',n:'needs_review'}[key]);}else if(key===' '&&active&&!items.find(i=>i.key===active).locked){e.preventDefault();checked.has(active)?checked.delete(active):checked.add(active);render();}});
function showTargeted(report){coverageData=report.coverage;renderTargetedPanel($('targetedContent'),report,feature=>{selectedCell=feature;group='all';$('queue').value='all';sampleKeys=null;priority=false;page=0;render();if(map&&feature){const [w,s,e,n]=feature.properties.bbox_wgs84;map.fitBounds([[w,s],[e,n]],{padding:30});}});$('targetedPanel').hidden=false;mapData();}
try{
  const response=await fetch('data/company-access-review/review-bundle.json');if(!response.ok)throw Error('历史审核数据不可用');historyBundle=await response.json();load(historyBundle);
  try{const r=await fetch('data/company-access-review/pilot3-coverage.geojson');if(r.ok)coverageData=await r.json();}catch{}
  try{const pending=await fetch('data/company-access-review/pending-review-bundle.json');if(pending.ok){const p=await fetch('data/company-access-review/second-pass.json');if(!p.ok)throw Error('二次筛选证据包不可用');defaultPack=await p.json();load(attachReviewHistory(await pending.json(),historyBundle),defaultPack);}}catch(error){status(`未加载新批次，历史数据保持不变：${error.message}`);}
  try{const r=await fetch('data/company-access-review/targeted-review-bundle.json');if(r.ok){
    const incoming=await r.json(),p=await fetch('data/company-access-review/targeted-second-pass.json');if(!p.ok)throw Error('缺少定向候选证据包');
    const pack=validateSecondPass(incoming,await p.json()),next=appendPending(bundle,incoming,historyBundle,session,currentPack),ids=new Set(pack.seeds.map(s=>s.poi_id));
    const combined={...next.pack,evidence:[...next.pack.evidence.filter(e=>!ids.has(e.poi_id)),...pack.evidence],seeds:[...next.pack.seeds.filter(s=>!ids.has(s.poi_id)),...pack.seeds]};
    load(next.bundle,combined,next.session,incoming.batches[0].id);
  }}catch(error){status(`定向批次未加载：${error.message}；原数据保持不变。`);}
  try{const r=await fetch('data/company-access-review/continuation-review-bundle.json');if(r.ok){const incoming=await r.json(),next=appendDiscovery(bundle,incoming,historyBundle,session,currentPack);load(next.bundle,next.pack,next.session,incoming.batches[0].id);}}catch(error){status(`续采批次未加载：${error.message}；原数据保持不变。`);}
  try{const r=await fetch('data/company-access-review/coverage-diagnostics.json');if(r.ok){const report=await r.json();renderCoveragePanel($('coverageContent'),report,feature=>{selectedCell=feature;group='all';$('queue').value='all';sampleKeys=null;priority=false;page=0;render();if(map&&feature){const [w,s,e,n]=feature.properties.bbox_wgs84;map.fitBounds([[w,s],[e,n]],{padding:30});}});$('coveragePanel').hidden=false;}}catch{status('覆盖诊断暂不可用；审核决定保持不变。');}
  try{const r=await fetch('data/company-access-review/targeted-readiness.json');if(r.ok)showTargeted(await r.json());}catch{status('定向采集诊断暂不可用；原有候选与决定保持不变。');}
  try { if(globalThis.maplibregl){map=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/positron',center:[121.604,31.205],zoom:12});map.on('load',()=>{map.addSource('candidates',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'candidate-points',type:'circle',source:'candidates',paint:{'circle-radius':['case',['get','selected'],10,6],'circle-color':['match',['get','status'],'accept','#285a50','reject','#888','needs_review','#b57c24','#bd3f55'],'circle-stroke-color':'#fff','circle-stroke-width':2}});ready=true;mapData();});map.on('click','candidate-points',e=>{if(e.features?.[0])select(e.features[0].properties.key);});}
  else status('地图暂不可用；列表、证据和审核导出仍可使用。');
  }catch{map=null;status('当前浏览器无法显示地图（可能未启用 WebGL）。列表、证据与审核导出仍可使用；没有改变任何决定。');}
}catch(e){status(e.message);}
