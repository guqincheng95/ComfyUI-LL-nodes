import { app } from '../../scripts/app.js';
import { LABELS, makeControl } from './controls.js';

export const SECTIONS = [
 {id:'exposure',label:'曝光',names:['exposure','contrast','highlights','shadows','whites','blacks']},
 {id:'temperature',label:'色温',names:['temperature','tint']},
 {id:'color',label:'色调',names:[...Object.keys(LABELS).filter(name=>!['exposure','contrast','highlights','shadows','whites','blacks','temperature','tint'].includes(name)),'preserve_luminosity']},
];

function makeBooleanControl(original,change){
 const element=document.createElement('label');
 element.style.cssText='display:flex;align-items:center;gap:10px;width:100%;min-width:0;max-width:100%;height:32px;min-height:0;margin:0;padding:0 10px;color:#ddd;font:12px/16px sans-serif;background:#282828;box-sizing:border-box;overflow:hidden;';
 const input=document.createElement('input');input.type='checkbox';input.checked=Boolean(original.value);
 input.style.cssText='box-sizing:border-box;flex:0 0 14px;width:14px;min-width:0;max-width:14px;height:14px;min-height:0;margin:0;padding:0;';
 const text=document.createElement('span');text.textContent='保持色彩平衡明度';
 text.style.cssText='min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
 input.setAttribute('aria-label','保持色彩平衡明度');
 input.addEventListener('change',()=>change(input.checked));
 for(const event of ['pointerdown','mousedown','keydown'])element.addEventListener(event,e=>e.stopPropagation());
 element.append(input,text);
 return {element,setValue(value){input.checked=Boolean(value);},setDisabled(disabled){input.disabled=disabled;}};
}

export function enhanceNode(node) {
 if(node.comfyClass !== 'AIVisualPhotoFinish' || node.__photoFinishUI) return;
 if(typeof node.addDOMWidget !== 'function') return;
 const controls=new Map(), groups=new Map(), records=[];
 const isOpen=id=>Boolean(node.properties?.llPhotoSections?.[id]);
 function resize(){
  node.setSize?.([Math.max(node.size?.[0]||360,280),node.computeSize()[1]]);
  node.setDirtyCanvas?.(true,true);
 }
 function refresh(){
  for(const {widget,element,section,header,control,original} of records){
   const open=isOpen(section.id);
   const visible=header || open;
   widget.hidden=!visible;
   // Older ComfyUI DOM hosts check type rather than the hidden flag.
   widget.type=visible?'photo_finish_number':'hidden';
   element.style.display=visible?'block':'none';
   control.element.style.display=open?(original.name==='preserve_luminosity'?'flex':'block'):'none';
   if(header){
    const changed=section.names.filter(name=>{
     const w=records.find(record=>record.original.name===name)?.original;
     return w && (name==='preserve_luminosity'?w.value!==true:Number(w.value)!==0);
    }).length;
    header.textContent=`${open?'▾':'▸'} ${section.label} · ${section.names.length} 项${changed?`（已调整 ${changed} 项）`:''}`;
    header.setAttribute('aria-expanded',String(open));
   }
  }
 }
 for(const section of SECTIONS){
  const first=section.names.find(name=>node.widgets?.some(widget=>widget.name===name));
  if(!first)continue;
  groups.set(section.id,section);
  for(const name of section.names){
   const original=node.widgets.find(widget=>widget.name===name);
   if(!original)continue;
   const index=node.widgets.indexOf(original);
   const change=value=>{
    node.graph?.beforeChange?.();original.value=value;
    original.callback?.call(original,value,app.canvas,node);
    node.graph?.afterChange?.();refresh();node.setDirtyCanvas?.(true,true);
   };
   const control=name==='preserve_luminosity'?makeBooleanControl(original,change):makeControl(name,original.value,change);
   controls.set(name,control);
   const element=document.createElement('div');
   // DOM host size is the full slot (margin:0 below). Keep the horizontal
   // inset inside our own border box so it is never subtracted from height.
   element.style.cssText='box-sizing:border-box;display:block;width:100%;min-width:0;max-width:100%;min-height:0;margin:0;padding:0 10px;overflow:hidden;';
   let header=null;
   if(name===first){
    header=document.createElement('button');header.type='button';
    header.setAttribute('aria-label',`${section.label}折叠区域`);
    header.style.cssText='box-sizing:border-box;display:block;width:100%;min-width:0;max-width:100%;height:30px;min-height:0;margin:0;background:#34434a;color:#eee;border:1px solid #5c737d;border-radius:5px;text-align:left;padding:0 10px;font:13px/28px sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;';
    header.addEventListener('click',()=>{
     node.graph?.beforeChange?.();node.properties??={};
     node.properties.llPhotoSections={...(node.properties.llPhotoSections||{}),[section.id]:!isOpen(section.id)};
     node.graph?.afterChange?.();refresh();resize();
    });
    for(const event of ['pointerdown','mousedown','keydown'])header.addEventListener(event,e=>e.stopPropagation());
    element.append(header);
   }
   element.append(control.element);
   const height=()=> (header?30:0) + (isOpen(section.id)?(name==='preserve_luminosity'?32:62):0);
   node.widgets.splice(index,1);
   const widget=node.addDOMWidget(name,'photo_finish_number',element,{
    // ComfyUI subtracts 2 * margin from the allocated DOM height. Our height
    // already describes the whole content, so the default margin of 10 leaves too little space.
    ...original.options,serialize:true,hideOnZoom:true,margin:0,
    getValue:()=>original.value,
    setValue:value=>{control.setValue(value);original.value=name==='preserve_luminosity'?Boolean(value):control.value;refresh();},
    getMinHeight:height,getMaxHeight:height,
    onDraw:()=>{
     control.setValue(original.value);
     control.setDisabled(Boolean(node.inputs?.some(input=>input.widget?.name===name && input.link!=null)));
     if(header)refresh();
    },
   });
   // Cancel LiteGraph's 4px row gap for fully hidden controls on older hosts.
   widget.computeSize=width=>[width??node.size?.[0]??360,widget.hidden?-4:height()];
   widget.serializeValue=()=>name==='preserve_luminosity'?Boolean(original.value):Number(original.value);
   node.widgets.splice(node.widgets.indexOf(widget),1);node.widgets.splice(index,0,widget);
   records.push({widget,element,section,header,control,original});
  }
 }
 node.__photoFinishUI={controls,groups,records,refresh,resize};
 refresh();resize();
}
app.registerExtension({
 name:'AIVisual.PhotoFinish.ReferenceAndSections',
 nodeCreated:enhanceNode,
 loadedGraphNode(node){
  enhanceNode(node);
  node.__photoFinishUI?.refresh();node.__photoFinishUI?.resize();
 },
});
