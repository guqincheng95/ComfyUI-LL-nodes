import { app } from '../../scripts/app.js';

// Reuse native widgets: values, slot order and serialization stay unchanged.
export function enhanceDlss(node) {
 if(node.comfyClass!=='LLDLSS5RegionEnhance'||node.__llDlssUI)return;
 const find=name=>node.widgets?.find(w=>w.name===name);
 if(!find('show_advanced'))return; // older backends need no UI adaptation
 const advanced=new Set(['model','style','tone','structure','skin_structure','automatic_skin_mask',
  'region_mode','person_strength','background_strength','lighting_strength','neutral_protection',
  'skin_protection','edge_guard','feather','mask_expand','temporal_mask_strength','runtime_dir',
  'release_comfy_models','worker_timeout','scene_change_threshold','auto_setup',
  'setup_archive','setup_index_url','setup_download_prefix','setup_wheel_dir','setup_http_proxy','setup_official_only']);
 const roi=new Set(['roi_x','roi_y','roi_width','roi_height']);
 const regionalNames=new Set(['region_mode','person_strength','background_strength','lighting_strength',
  'neutral_protection','skin_protection','edge_guard','feather','mask_expand','temporal_mask_strength']);
 const controlled=new Set([...advanced,...roi,'preview_long_edge','preset','upscaling','show_advanced']);
 const records=node.widgets.filter(w=>controlled.has(w.name)).map(widget=>({widget,type:widget.type,computeSize:widget.computeSize}));
 const refresh=()=>{
  const linked=name=>node.inputs?.some(input=>input.name===name&&input.link!=null);
  const legacy=linked('settings');
  const mode=find('processing_mode')?.value||'auto';
  const region=mode==='regional'||(mode==='auto'&&(legacy||linked('person_mask')||linked('skin_mask')||['人像保真','均衡增强','环境增强'].includes(find('preset')?.value)));
  for(const record of records){
   const name=record.widget.name;
   let visible;
   if(roi.has(name))visible=Boolean(find('compare_preview')?.value);
   else if(name==='preview_long_edge')visible=Boolean(find('preview_mode')?.value);
   else if(['preset','upscaling','show_advanced'].includes(name))visible=!legacy;
   else visible=!legacy&&Boolean(find('show_advanced')?.value)&&(!regionalNames.has(name)||region);
   if(['temporal_mask_strength','scene_change_threshold'].includes(name))visible=visible&&find('batch_mode')?.value==='video_sequence';
   if(name.startsWith('setup_'))visible=visible&&Boolean(find('auto_setup')?.value);
   record.widget.hidden=!visible;
   record.widget.type=visible?record.type:'converted-widget';
   if(visible){if(record.computeSize)record.widget.computeSize=record.computeSize;else delete record.widget.computeSize;}
   else record.widget.computeSize=()=>[0,-4];
  }
  node.setSize?.([node.size?.[0]||380,node.computeSize()[1]]);
  node.setDirtyCanvas?.(true,true);
 };
 for(const name of ['show_advanced','compare_preview','preview_mode','processing_mode','batch_mode','auto_setup']){
  const widget=find(name);if(!widget)continue;
  const old=widget.callback;widget.callback=function(...args){const result=old?.apply(this,args);refresh();return result;};
 }
 const preset=find('preset');
 if(preset){
  const old=preset.callback;
  preset.callback=function(...args){
   const result=old?.apply(this,args);
   const values={
    '原生默认':[1,1.5,2,.35,1,.7], '人像保真':[1,1.2,.6,.35,.9,.65],
    '均衡增强':[1,1.3,.8,.55,.85,.75], '环境增强':[1.2,1.6,.6,.3,1,.85],
   }[this.value];
   if(values){
    ['tone','structure','skin_structure','person_strength','background_strength','lighting_strength']
     .forEach((name,index)=>{const w=find(name);if(w)w.value=values[index];});
    for(const [name,value] of Object.entries({neutral_protection:.35,skin_protection:.6,edge_guard:.7,region_mode:'unified_lighting'})){
     const w=find(name);if(w)w.value=value;
    }
   }
   refresh();return result;
  };
 }
 for(const name of ['tone','structure','skin_structure',...regionalNames]){
  const widget=find(name);if(!widget)continue;
  const old=widget.callback;widget.callback=function(...args){
   const result=old?.apply(this,args);
   if(preset&&['人像保真','均衡增强','环境增强'].includes(preset.value)){
    preset.value='自定义';
    const mode=find('processing_mode');if(mode?.value==='auto')mode.value='regional';
   }
   refresh();return result;
  };
 }
 const oldConnection=node.onConnectionsChange;
 node.onConnectionsChange=function(...args){const result=oldConnection?.apply(this,args);refresh();return result;};
 node.__llDlssUI={refresh,records};refresh();
}
app.registerExtension({name:'LL.DLSS5.SingleNode',nodeCreated:enhanceDlss,
 loadedGraphNode(node){enhanceDlss(node);node.__llDlssUI?.refresh();}});
