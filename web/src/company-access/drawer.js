import {createCompanySearchIndex} from './search.js';
import {reviewStatusLabel,reviewCandidateHref} from './candidate-search.js';
const confidence={verified:'Verified physical office',building:'Reviewed mapped office',approximate:'Approximate location'};
export function searchOffices(offices,query){
  return createCompanySearchIndex(offices)(query);
}
/** Dedicated map overlay; only the list scrolls. Provider text is never HTML. */
export class CompanyDrawer {
  constructor({root,onHighlight=()=>{},onCandidate=()=>{},onClose=()=>{}}){
    this.onHighlight=onHighlight;this.onCandidate=onCandidate;this.onClose=onClose;this.offices=[];this.inventory=[];this.candidates=[];
    const doc=root.ownerDocument;
    this.element=doc.createElement('aside');this.element.className='company-drawer';this.element.hidden=true;
    this.element.setAttribute('role','dialog');this.element.setAttribute('aria-label','Company office details');
    this.element.innerHTML=`<header><div><p class="company-drawer-eyebrow">COMPANY ACCESS · REVIEW</p><h2 id="companyDrawerHeading"></h2></div><button type="button" aria-label="Close company details" class="company-drawer-close">×</button></header><div class="company-drawer-search"><label for="companyDrawerSearch">Find a company</label><input id="companyDrawerSearch" type="search" placeholder="Company, address or district" autocomplete="off"><p class="company-drawer-count" role="status" aria-live="polite"></p></div><div class="company-drawer-list"></div><footer>Identified offices in a limited pilot. Missing inventory does not mean no offices.</footer>`;
    root.append(this.element);
    this.heading=this.element.querySelector('h2');this.input=this.element.querySelector('input');this.list=this.element.querySelector('.company-drawer-list');this.count=this.element.querySelector('.company-drawer-count');
    this.input.placeholder='公司 / SMIC / 华虹 / SAP / NVIDIA';
    const quick=doc.createElement('div');quick.className='company-search-shortcuts';
    for(const name of ['中芯国际','华虹','环旭','豪威']){const button=doc.createElement('button');button.type='button';button.textContent=name;button.addEventListener('click',()=>{this.input.value=name;this.render();});quick.append(button);}
    this.input.parentNode.append(quick);
    this.element.querySelector('button').addEventListener('click',()=>this.close());
    this.input.addEventListener('input',()=>this.render());
    this.element.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();this.close();}});
  }
  setInventory(offices,candidates){this.inventory=offices;this.candidates=candidates;}
  open(selection){
    if(this.element.hidden)this.previousFocus=this.element.ownerDocument.activeElement;
    this.browse=selection.kind==='inventory';
    this.offices=['cluster','inventory'].includes(selection.kind)?selection.offices:[selection];this.selected=selection.kind==='cluster'?null:selection.id;
    this.heading.textContent=selection.kind==='cluster'?`${this.offices.length} offices in this cluster`:'Office details';
    this.input.value='';this.element.hidden=false;this.render();this.input.focus({preventScroll:true});
  }
  render(){
    const searching=this.input.value.trim()||this.browse;
    const visible=searchOffices(searching?[...this.candidates.filter(c=>c.priority_evidence),...this.inventory,...this.candidates.filter(c=>!c.priority_evidence)]:this.offices,this.input.value),doc=this.element.ownerDocument;
    const approved=visible.filter(o=>o.kind!=='candidate').length;
    this.count.textContent=`${approved} 已批准（当前范围） · ${visible.length-approved} 候选（全部范围）${visible.length>60?' · 显示前60条，请搜索缩小范围':''}`;this.list.replaceChildren();
    const text=(parent,tag,value,className)=>{const e=doc.createElement(tag);e.textContent=value;if(className)e.className=className;parent.append(e);return e;};
    if(!visible.length)text(this.list,'p','No matching offices. Try a different name or address.','company-drawer-empty');
    for(const office of visible.slice(0,60)){
      const card=doc.createElement('button');card.type='button';card.className='company-office-card';card.setAttribute('aria-pressed',String(this.selected===office.id));
      text(card,'strong',office.company_name,'company-office-name');text(card,'span',office.address||'Address not supplied','company-office-address');
      const candidate=office.kind==='candidate';
      text(card,'span',candidate?reviewStatusLabel[office.review_status]:'已批准办公室','company-review-badge');
      text(card,'span',`${office.district||'Unknown district'} · ${candidate?'AMap地点，尚未批准为办公室':confidence[office.location_confidence]||office.location_confidence}`,'company-office-meta');
      if(candidate){
        card.classList.add('company-candidate-card');
        const minutes=this.limit==='all'?50:this.limit;
        text(card,'span',office.reach_minutes.includes(minutes)?`在当前${minutes}分钟范围内 · 不计入办公室数量`:`当前范围外 · 最早${office.reach_minutes[0]||'未进入50'}分钟 · 不计入办公室数量`,'company-office-meta');
        if(office.priority_evidence){text(card,'span',office.priority_evidence.finding,'company-office-meta');text(card,'span',office.priority_evidence.action,'company-office-meta');}
      }
      // Canonical pipeline only supplies these fields with supporting evidence.
      if(office.building_name)text(card,'span',office.building_name,'company-office-meta');
      if(office.sector)text(card,'span',office.sector,'company-office-meta');
      card.addEventListener('click',()=>{this.selected=office.id;for(const child of this.list.children)child.setAttribute('aria-pressed','false');card.setAttribute('aria-pressed','true');candidate?this.onCandidate(office):this.onHighlight(office.id);});
      this.list.append(card);
      if(candidate){const a=text(this.list,'a',office.locked?'查看已锁定决定与证据 ↗':'定位后进入审核 ↗','company-review-link');a.href=reviewCandidateHref(office.amap_poi_id);a.target='_blank';a.rel='noopener';}
    }
  }
  sync(limit,visible){if(this.limit!==limit||!visible)this.close();this.limit=limit;}
  close(){const wasOpen=!this.element.hidden;this.element.hidden=true;this.onClose();if(wasOpen&&this.previousFocus?.isConnected)this.previousFocus.focus({preventScroll:true});}
}
