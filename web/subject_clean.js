import { app } from '../../scripts/app.js';

// Keep native widgets and their order/serialization. Skin switch reveals advanced controls.
export function enhanceSubject(node) {
 if(node.comfyClass!=='LLPersonSubjectClean'||node.__llSubjectUI)return;
 const toggle=node.widgets?.find(w=>w.name==='skin_enabled');
 if(!toggle)return;
 const records=node.widgets.filter(w=>['skin_strength','skin_band','skin_protection'].includes(w.name))
  .map(widget=>({widget,type:widget.type,computeSize:widget.computeSize}));
 const refresh=()=>{
  for(const record of records){
   record.widget.hidden=!toggle.value;
   record.widget.type=toggle.value?record.type:'converted-widget';
   if(toggle.value){
    if(record.computeSize)record.widget.computeSize=record.computeSize;
    else delete record.widget.computeSize;
   }else record.widget.computeSize=()=>[0,-4];
  }
  node.setSize?.([node.size?.[0]||380,node.computeSize()[1]]);
  node.setDirtyCanvas?.(true,true);
 };
 const old=toggle.callback;
 toggle.callback=function(...args){const result=old?.apply(this,args);refresh();return result;};
 node.__llSubjectUI={refresh,records};refresh();
}
app.registerExtension({name:'LL.SubjectClean.SkinControls',nodeCreated:enhanceSubject,
 loadedGraphNode(node){enhanceSubject(node);node.__llSubjectUI?.refresh();}});
