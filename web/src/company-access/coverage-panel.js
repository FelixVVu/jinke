const labels={approved:'已批准',recovered_pending:'缓存恢复 · 待人工确认',historical_decision_locked:'历史决定锁定',unresolved_name_hit:'名称命中，身份未绑定',not_returned_in_cached_queries:'原始缓存未返回'};
const cellLabels={coarse_only_no_fine_query:'无细网格查询（曾有粗网格采样）',failed_incomplete:'请求失败 · 不完整',saturated_incomplete:'满页截断 · 不完整',sampled_partial:'已抽样 · 仍不完整'};
const add=(parent,tag,value)=>{const e=document.createElement(tag);e.textContent=value;parent.append(e);return e;};
export function renderCoveragePanel(root,report,onCell){
  root.replaceChildren();const s=report.summary;
  add(root,'p',`已批准 ${s.approved} · 历史锁定 ${s.historical_decisions} · 缓存新线索 ${s.new_pending} · 本次 API 调用 ${s.new_api_requests}`);
  add(root,'p',`${s.cells} 格中的细网格进度：成功 ${s.fine_sampled}，未查询 ${s.fine_unqueried}，失败 ${s.fine_failed}；${s.saturated} 格返回满页。已证实空区域：${s.verified_empty}。`);
  add(root,'p',report.notice);
  add(root,'p','地图图例：灰色＝尚无细网格成功查询；橙色＝满页截断；红色＝请求失败；绿色＝已有部分采样。所有颜色都不代表完整清单。');
  const label=add(root,'label','定位与筛选区域');const select=document.createElement('select');label.append(select);select.add(new Option('全部 30 分钟区域',''));
  for(const f of [...report.coverage.features].sort((a,b)=>b.properties.recovered_pending-a.properties.recovered_pending)){
    const p=f.properties;select.add(new Option(`${p.cell_id} · ${p.approved} 已批 / ${p.recovered_pending} 新线索 · ${cellLabels[p.status]}`,p.cell_id));}
  select.onchange=()=>onCell(report.coverage.features.find(f=>f.properties.cell_id===select.value)||null);
  add(root,'h3','代表公司追踪（诊断样本，不是总体完整率）');
  add(root,'p',`${s.benchmark_total} 个目标：${s.benchmark_approved} 已批准，${s.benchmark_recovered} 恢复待审；${s.benchmark_total-s.benchmark_located} 个没有可绑定的范围内坐标，不纳入空间召回分母。`);
  const table=document.createElement('table'),head=document.createElement('tr');for(const t of ['公司 / 公开线索','遗漏阶段','原始排除与证据限制'])add(head,'th',t);table.append(head);
  for(const b of report.benchmark){const row=document.createElement('tr');const name=add(row,'td',b.company_name);for(const source of b.sources||[]){try{const u=new URL(source.url);if(u.protocol!=='https:'||u.username||u.password)continue;const a=add(name,'a',source.title+' ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}catch{}}
    add(row,'td',labels[b.stage]||b.stage);add(row,'td',[...new Set(b.trace.flatMap(t=>t.original_exclusions))].join(' / ')+' '+b.limitations);table.append(row);}
  root.append(table);add(root,'p','下一轮计划优先细分缺口网格，按公司名搜索补漏，包含企业与科研类别；计划尚未执行。公司官网、园区目录用于发现和证据，旧参考图不证明当前在驻。');
  for(const warning of report.source_limitations||[])add(root,'small',warning);
}
export const insideCoverageCell=(item,feature)=>{if(!feature)return true;const [w,s,e,n]=feature.properties.bbox_wgs84;return +item.row.longitude_wgs84>=w&&+item.row.longitude_wgs84<=e&&+item.row.latitude_wgs84>=s&&+item.row.latitude_wgs84<=n;};
