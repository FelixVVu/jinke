import {aliasTerms} from './aliases.js';
const confidence={verified:'Verified physical office',building:'Reviewed mapped office',approximate:'Approximate location'};
export function searchOffices(offices,query){
  const q=query.normalize('NFKC').trim().toLocaleLowerCase();
  return offices.filter(o=>[o.company_name,...aliasTerms(o),o.address,o.district,o.building_name,o.sector].filter(Boolean).join(' ').normalize('NFKC').toLocaleLowerCase().includes(q));
}
/** Dedicated map overlay; only the list scrolls. Provider text is never HTML. */
export class CompanyDrawer {
  constructor({root,onHighlight=()=>{},onClose=()=>{}}){
    this.onHighlight=onHighlight;this.onClose=onClose;this.offices=[];
    const doc=root.ownerDocument;
    this.element=doc.createElement('aside');this.element.className='company-drawer';this.element.hidden=true;
    this.element.setAttribute('role','dialog');this.element.setAttribute('aria-label','Company office details');
    this.element.innerHTML=`<header><div><p class="company-drawer-eyebrow">COMPANY ACCESS · REVIEW</p><h2 id="companyDrawerHeading"></h2></div><button type="button" aria-label="Close company details" class="company-drawer-close">×</button></header><div class="company-drawer-search"><label for="companyDrawerSearch">Find a company</label><input id="companyDrawerSearch" type="search" placeholder="Company, address or district" autocomplete="off"><p class="company-drawer-count" role="status" aria-live="polite"></p></div><div class="company-drawer-list"></div><footer>Identified offices in a limited pilot. Missing inventory does not mean no offices.</footer>`;
    root.append(this.element);
    this.heading=this.element.querySelector('h2');this.input=this.element.querySelector('input');this.list=this.element.querySelector('.company-drawer-list');this.count=this.element.querySelector('.company-drawer-count');
    this.element.querySelector('button').addEventListener('click',()=>this.close());
    this.input.addEventListener('input',()=>this.render());
    this.element.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();this.close();}});
  }
  open(selection){
    if(this.element.hidden)this.previousFocus=this.element.ownerDocument.activeElement;
    this.offices=selection.kind==='cluster'?selection.offices:[selection];this.selected=selection.kind==='cluster'?null:selection.id;
    this.heading.textContent=selection.kind==='cluster'?`${this.offices.length} offices in this cluster`:'Office details';
    this.input.value='';this.element.hidden=false;this.render();this.input.focus({preventScroll:true});
  }
  render(){
    const visible=searchOffices(this.offices,this.input.value),doc=this.element.ownerDocument;
    this.count.textContent=`${visible.length} of ${this.offices.length} identified offices`;this.list.replaceChildren();
    const text=(parent,tag,value,className)=>{const e=doc.createElement(tag);e.textContent=value;if(className)e.className=className;parent.append(e);return e;};
    if(!visible.length)text(this.list,'p','No matching offices. Try a different name or address.','company-drawer-empty');
    for(const office of visible){
      const card=doc.createElement('button');card.type='button';card.className='company-office-card';card.setAttribute('aria-pressed',String(this.selected===office.id));
      text(card,'strong',office.company_name,'company-office-name');text(card,'span',office.address||'Address not supplied','company-office-address');
      text(card,'span',`${office.district||'Unknown district'} · ${confidence[office.location_confidence]||office.location_confidence}`,'company-office-meta');
      // Canonical pipeline only supplies these fields with supporting evidence.
      if(office.building_name)text(card,'span',office.building_name,'company-office-meta');
      if(office.sector)text(card,'span',office.sector,'company-office-meta');
      card.addEventListener('click',()=>{this.selected=office.id;for(const child of this.list.children)child.setAttribute('aria-pressed','false');card.setAttribute('aria-pressed','true');this.onHighlight(office.id);});
      this.list.append(card);
    }
  }
  sync(limit,visible){if(this.limit!==limit||!visible)this.close();this.limit=limit;}
  close(){const wasOpen=!this.element.hidden;this.element.hidden=true;this.onClose();if(wasOpen&&this.previousFocus?.isConnected)this.previousFocus.focus({preventScroll:true});}
}
