import { app } from '../../scripts/app.js';

// Keep native widgets and their order/serialization. Toggle advanced fields in place.
export function enhanceSubject(node) {
 if(!['LLPersonSubjectClean','LLPersonContourTrim'].includes(node.comfyClass)||node.__llSubjectUI)return;
 const groups=[['skin_enabled',['skin_strength','skin_band','skin_protection']],
  ['foot_protection',['foot_scale']],['hand_protection',['hand_scale']]]
  .map(([name,names])=>({toggle:node.widgets?.find(w=>w.name===name),names})).filter(g=>g.toggle);
 if(!groups.length)return;
 const records=groups.flatMap(({toggle,names})=>node.widgets.filter(w=>names.includes(w.name))
  .map(widget=>({widget,toggle,type:widget.type,computeSize:widget.computeSize})));
 const refresh=()=>{
  for(const record of records){
   record.widget.hidden=!record.toggle.value;
   record.widget.type=record.toggle.value?record.type:'converted-widget';
   if(record.toggle.value){
    if(record.computeSize)record.widget.computeSize=record.computeSize;
    else delete record.widget.computeSize;
   }else record.widget.computeSize=()=>[0,-4];
  }
  node.setSize?.([node.size?.[0]||380,node.computeSize()[1]]);
  node.setDirtyCanvas?.(true,true);
 };
 for(const {toggle} of groups){
  const old=toggle.callback;
  toggle.callback=function(...args){const result=old?.apply(this,args);refresh();return result;};
 }
 node.__llSubjectUI={refresh,records};refresh();
}
app.registerExtension({name:'LL.SubjectClean.SkinControls',nodeCreated:enhanceSubject,
 loadedGraphNode(node){enhanceSubject(node);node.__llSubjectUI?.refresh();}});
