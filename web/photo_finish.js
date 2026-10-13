import { app } from '../../scripts/app.js';
import { LABELS, makeControl } from './controls.js';

export function enhanceNode(node) {
 if(node.comfyClass !== 'AIVisualPhotoFinish' || node.__photoFinishV2) return;
 if(typeof node.addDOMWidget !== 'function') return; // Native controls remain usable.
 node.__photoFinishV2=true;
 for(const original of [...(node.widgets || [])]) {
  if(!Object.hasOwn(LABELS,original.name)) continue;
  const index=node.widgets.indexOf(original);
  let widget;
  const control=makeControl(original.name,original.value,value=>{
   node.graph?.beforeChange?.();
   original.value=value;
   original.callback?.call(original,value,app.canvas,node);
   node.graph?.afterChange?.();
   node.setDirtyCanvas?.(true,true);
  });
  node.widgets.splice(index,1);
  widget=node.addDOMWidget(original.name,'photo_finish_number',control.element,{
   ...original.options,serialize:true,hideOnZoom:true,
   getValue:()=>original.value,
   setValue:value=>{control.setValue(value);original.value=control.value;},
   getMinHeight:()=>62,getMaxHeight:()=>62,
   onDraw:()=>{
    control.setValue(original.value);
    const connected=node.inputs?.some(input=>input.widget?.name===original.name && input.link!=null);
    control.setDisabled(Boolean(connected));
   },
  });
  widget.computeSize=width=>[width,62];
  widget.serializeValue=()=>Number(original.value);
  // Replace in place: same name, count and ordering as v1 numeric widgets.
  node.widgets.splice(node.widgets.indexOf(widget),1);
  node.widgets.splice(index,0,widget);
 }
 node.setSize?.([Math.max(node.size?.[0]||0,360),node.computeSize()[1]]);
}
app.registerExtension({
 name:'AIVisual.PhotoFinish.SlidersV2',
 nodeCreated:enhanceNode,
 loadedGraphNode(node){
  enhanceNode(node);
  if(node.comfyClass==='AIVisualPhotoFinish') node.setSize?.([Math.max(node.size[0],360),Math.max(node.size[1],node.computeSize()[1])]);
 },
});
