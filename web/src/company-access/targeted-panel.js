const add=(root,tag,value)=>{const e=document.createElement(tag);e.textContent=value;root.append(e);return e;};
const statuses={unsampled:'尚未查询',failed_incomplete:'失败／未完成',sampled_partial:'已取样，非完整清单',saturated_incomplete:'满页到上限，仍有遗漏',pagination_incomplete:'满页，等待续页'};
export function renderTargetedPanel(root,report,onCell){
  root.replaceChildren();add(root,'h3','截图缺口优先 · 30 分钟定向发现');
  if(report.review_import)add(root,'p',`审核已导入：新增 ${report.review_import.human_accepts} 家，总计 ${report.review_import.canonical_offices} 家办公室。下方原始采集统计保留作审计；已接受记录在历史中锁定，其余候选保持待审。`);
  add(root,'p',`16 个细格 / 四个红框 + 中芯国际、华虹、环旭名称搜索。${report.api_requests_total||0} 次新请求，${report.candidate_review_count||0} 条本轮新待审。原有 145 家办公室、442 条决定及 291 条恢复线索不变。`);
  add(root,'p','当前重点是发现覆盖率，无需现在审核 291 条恢复线索。每次最多 24 次、累计最多 48 次请求（含重试），独立检查点，不重跑 Pilot 3。');
  if(report.continuation){
    const c=report.continuation;add(root,'p',`已分析 ${report.triage.analyzed} 条：可信候选 ${report.triage.groups.trusted||0}，重点核实 ${report.triage.groups.exception||0}，建议排除 ${report.triage.groups.exclude||0}。全部仍待人工决定。`);
    add(root,'p',`采集暂停：${report.stop_reason}。已用 ${c.attempts_spent}/48 次，剩余 ${c.attempts_remaining} 次；${c.next_pages.filter(q=>q.kind==='geographic').length} 个地理细格等待续页，另 ${c.cached_overflow_ids.length} 条保留在离线上限审计中。不要重跑当前工作流；建议分组不释放候选上限。续页计划保留全部缓存与请求历史，尚未启用。`);
    add(root,'p','本轮 300 条已在下方独立批次中；批量操作只作用于所选批次。原 291 条恢复线索无需现在处理。');
  }else{
    const launch=add(root,'a','打开现有 GitHub Actions → Run workflow → 选择 review/company-access-scaffold');launch.href='https://github.com/FelixVVu/jinke/actions/workflows/company-access-amap-pilot.yml';launch.target='_blank';launch.rel='noopener noreferrer';
    add(root,'p',`状态：${report.stop_reason||'READY_NOT_DISPATCHED'}。再次运行须用新的 Run workflow，不要 Re-run jobs。`);
  }
  const label=add(root,'label','定位截图优先细格'),select=document.createElement('select');label.append(select);select.add(new Option('全部优先区域',''));
  for(const f of report.coverage.features){const p=f.properties;select.add(new Option(`${p.cell_id} · ${statuses[p.status]||p.status}`,p.cell_id));}
  select.onchange=()=>onCell(report.coverage.features.find(f=>f.properties.cell_id===select.value)||null);
  const table=document.createElement('table'),head=document.createElement('tr');for(const s of ['区域','已批准 / 已知待审','本轮采样'])add(head,'th',s);table.append(head);
  for(const r of report.baseline_regions||[]){const cells=report.coverage.features.filter(f=>f.properties.region_id===r.id),sampled=cells.filter(f=>f.properties.pages?.length).length,incomplete=cells.filter(f=>f.properties.status==='pagination_incomplete').length;const tr=document.createElement('tr');for(const s of [r.label,`${r.approved} / ${r.pending_recovery}`,`${sampled}/4 已查询 · ${incomplete} 满页待续`])add(tr,'td',s);table.append(tr);}root.append(table);
  add(root,'p',`本轮代表名称命中：${report.discovery_name_hit_rate.numerator}/${report.discovery_name_hit_rate.denominator}（名称线索，不是已核实实体召回率）。未定位公司不当作空间召回的零值；任何空结果都不等于区域没有公司。`);
  if(report.previous_summary){const s=report.previous_summary;add(root,'p',`原缓存代表公司基准：${s.benchmark_total} 个目标，${s.benchmark_located} 个已绑定范围内 POI，其中 ${s.benchmark_approved} 已批准、${s.benchmark_recovered} 恢复待审；余下未定位。中芯国际原缓存未返回，华虹曾被 10 分钟裁剪排除，环旭曾被多类别过滤排除。`);}
  for(const b of report.benchmark){const row=add(root,'details','');add(row,'summary',`${b.company_name} · ${b.recall_status}`);add(row,'p',b.address_lead||'');add(row,'p',b.limitations);for(const s of b.sources){try{const u=new URL(s.url);if(u.protocol!=='https:'||u.username||u.password)continue;const a=add(row,'a',s.title+' ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}catch{}}}
  if(report.benchmark_findings?.length){add(root,'h3','代表公司：POI 命中与办公室确认分开');for(const b of report.benchmark_findings){const row=add(root,'details','');add(row,'summary',`${b.name} · ${b.status}`);add(row,'p',b.detail);add(row,'p',`本轮新增人工确认办公室：${b.confirmed_offices}。关联 POI：${b.poi_ids.join(' / ')||'尚未定位'}`);for(const s of b.sources){const u=new URL(s.url);if(u.protocol==='https:'){const a=add(row,'a',s.title+' ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}}}}
  add(root,'p','矩形范围由截图地铁站锚点近似对齐，仅决定查询优先级。最终候选仍使用原有 GCJ02→WGS84 转换及精确 30 分钟多边形裁剪。历史图和园区孵化名单不证明当前在驻。');
}
