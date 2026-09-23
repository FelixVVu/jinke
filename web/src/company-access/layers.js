import { selectCompanyOffices } from './model.js';
export const COMPANY_SOURCE = 'company-access-offices';
export const COMPANY_LAYER = 'company-access-circles';
export const CLUSTER_LAYER = 'company-access-clusters';
export const COUNT_LAYER = 'company-access-counts';
export const HUB_SOURCE = 'company-access-hubs';
export const HUB_LAYER = 'company-access-hub-labels';
export const withCompanyGlyphs = style => ({...style,glyphs:style.glyphs||'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'});

/** One controller per Map. Sources are filtered BEFORE MapLibre clusters them. */
export class CompanyAccessLayers {
  constructor(map,onSelect=()=>{}){
    Object.assign(this,{map,onSelect,output:null,limit:50,visible:false,bound:false,generation:0});
    this.handlers={mouseenter:()=>{map.getCanvas().style.cursor='pointer';},mouseleave:()=>{map.getCanvas().style.cursor='';},click:event=>{
      const id=event.features?.[0]?.id;
      const office=selectCompanyOffices(this.output,this.limit).features.find(f=>f.id===id);
      if(office&&this.visible)this.onSelect(office.properties);
    }};
    this.clusterHandlers={...this.handlers,click:async event=>{
      const feature=event.features?.[0],source=map.getSource(COMPANY_SOURCE),generation=this.generation;
      if(!feature||!source||!this.visible)return;
      try{
        const leaves=await source.getClusterLeaves(feature.properties.cluster_id,this.output.offices.features.length,0);
        if(generation!==this.generation||source!==map.getSource(COMPANY_SOURCE)||!this.visible)return;
        const ids=new Set(leaves.map(f=>f.id));
        const offices=selectCompanyOffices(this.output,this.limit).features.filter(f=>ids.has(f.id)).map(f=>f.properties);
        this.onSelect({kind:'cluster',office_count:offices.length,offices});
      }catch{/* Style replacement invalidates pending cluster queries. */}
    }};
  }
  setState({output=this.output,limit=this.limit,visible=this.visible}={}){
    selectCompanyOffices(output,limit);
    if(output!==this.output||limit!==this.limit||visible!==this.visible)this.generation++;
    Object.assign(this,{output,limit,visible:Boolean(visible&&output?.metadata.status==='ready')});this.restore();
  }
  restore(){
    const map=this.map;if(!map.getStyle()||!map.getLayer('station-circle'))return false;
    const data=selectCompanyOffices(this.output,this.limit),minutes=this.limit==='all'?50:this.limit;
    if(!map.getSource(COMPANY_SOURCE)){this.generation++;map.addSource(COMPANY_SOURCE,{type:'geojson',data,cluster:true,clusterRadius:48,clusterMaxZoom:14});}
    else if(this.lastOutput!==this.output||this.lastLimit!==this.limit)map.getSource(COMPANY_SOURCE).setData(data);
    this.lastOutput=this.output;this.lastLimit=this.limit;
    const hubs={type:'FeatureCollection',features:(this.output?.hubs.features||[]).filter(f=>f.properties.counts_by_reach[minutes]>0&&f.properties.hub_kind!=='spatial_cluster')};
    if(!map.getSource(HUB_SOURCE))map.addSource(HUB_SOURCE,{type:'geojson',data:hubs});else map.getSource(HUB_SOURCE).setData(hubs);
    const layers=[
      {id:CLUSTER_LAYER,type:'circle',source:COMPANY_SOURCE,filter:['has','point_count'],paint:{'circle-color':'#bd3f55','circle-radius':['step',['get','point_count'],19,10,24,25,29],'circle-stroke-color':'#fff','circle-stroke-width':3,'circle-opacity':0.96}},
      {id:COUNT_LAYER,type:'symbol',source:COMPANY_SOURCE,filter:['has','point_count'],layout:{'text-field':['to-string',['get','point_count']],'text-font':['Noto Sans Regular'],'text-size':15,'text-allow-overlap':true},paint:{'text-color':'#fff'}},
      {id:COMPANY_LAYER,type:'circle',source:COMPANY_SOURCE,filter:['!',['has','point_count']],paint:{'circle-color':'#bd3f55','circle-radius':6,'circle-stroke-color':'#fff','circle-stroke-width':2}},
      {id:HUB_LAYER,type:'symbol',source:HUB_SOURCE,minzoom:11,layout:{'text-field':['get','hub_name'],'text-font':['Noto Sans Regular'],'text-size':12,'text-offset':[0,1.2]},paint:{'text-color':'#733442','text-halo-color':'#fff','text-halo-width':2}},
    ];
    for(const layer of layers){if(!map.getLayer(layer.id))map.addLayer(layer,'station-circle');map.setLayoutProperty(layer.id,'visibility',this.visible?'visible':'none');}
    if(!this.bound){for(const [layer,handlers] of [[COMPANY_LAYER,this.handlers],[CLUSTER_LAYER,this.clusterHandlers]])for(const [event,handler] of Object.entries(handlers))map.on(event,layer,handler);this.bound=true;}
    return true;
  }
  destroy(){
    this.generation++;
    if(this.bound)for(const [layer,handlers] of [[COMPANY_LAYER,this.handlers],[CLUSTER_LAYER,this.clusterHandlers]])for(const [event,handler] of Object.entries(handlers))this.map.off(event,layer,handler);
    this.bound=false;this.map.getCanvas().style.cursor='';
    for(const id of [HUB_LAYER,COMPANY_LAYER,COUNT_LAYER,CLUSTER_LAYER])if(this.map.getLayer(id))this.map.removeLayer(id);
    for(const id of [HUB_SOURCE,COMPANY_SOURCE])if(this.map.getSource(id))this.map.removeSource(id);
  }
}
