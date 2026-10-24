import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const app={registerExtension(extension){this.extension=extension;}};
globalThis.__subjectTestApp=app;
const source=(await fs.readFile(new URL('../web/subject_clean.js',import.meta.url),'utf8'))
 .replace("import { app } from '../../scripts/app.js';",'const app=globalThis.__subjectTestApp;');
const {enhanceSubject}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const node={comfyClass:'LLPersonSubjectClean',size:[380,500],widgets:[
 {name:'skin_enabled',type:'toggle',value:false},
 {name:'skin_strength',type:'number',value:.65},
 {name:'skin_band',type:'number',value:12},
 {name:'skin_protection',type:'number',value:.8},
 {name:'feather',type:'number',value:1},
],computeSize(){return [380,400];},setSize(size){this.size=size;},setDirtyCanvas(){}};
const values=node.widgets.map(w=>w.value);enhanceSubject(node);
assert.equal(node.widgets.length,5);assert.equal(node.widgets[1].hidden,true);
assert.deepEqual(node.widgets[1].computeSize(),[0,-4]);
node.widgets[0].value=true;node.widgets[0].callback(true);
assert.equal(node.widgets[1].type,'number');assert.equal(node.widgets[1].hidden,false);
assert.equal(node.widgets[1].computeSize,undefined);
node.widgets[0].value=false;app.extension.loadedGraphNode(node);
assert.deepEqual(node.widgets.map(w=>w.value),values);assert.equal(node.widgets[4].hidden,undefined);
const callback=node.widgets[0].callback;enhanceSubject(node);assert.equal(node.widgets[0].callback,callback);
console.log('PASS: skin switch expands/collapses 3 native controls, keeps values/order, restores loaded state, idempotent.');
for(const comfyClass of ['LLPersonSubjectClean','LLPersonContourTrim']){
 const originalCallback=()=>{};
 const n={comfyClass,size:[320,500],widgets:[
  {name:'feather',type:'number',value:1},
  {name:'foot_protection',type:'toggle',value:true,callback:originalCallback},
  {name:'foot_scale',type:'number',value:1.6},
  {name:'hand_protection',type:'toggle',value:false},
  {name:'hand_scale',type:'number',value:1.3},
 ],computeSize(){return [320,400];},setSize(size){this.size=size;},setDirtyCanvas(){}};
 const names=n.widgets.map(w=>w.name),values=n.widgets.map(w=>w.value);
 enhanceSubject(n);enhanceSubject(n);
 assert.equal(n.widgets[2].hidden,false);assert.equal(n.widgets[4].hidden,true);
 n.widgets[1].value=false;n.widgets[1].callback(false);
 assert.deepEqual(n.widgets[2].computeSize(),[0,-4]);
 assert.equal(n.widgets[4].hidden,true,'hand switch remains independent');
 n.widgets[3].value=true;n.widgets[3].callback(true);
 assert.equal(n.widgets[4].type,'number');assert.equal(n.widgets[2].hidden,true);
 n.widgets[1].value=true;n.widgets[3].value=false;
 app.extension.loadedGraphNode(n);
 assert.deepEqual(n.widgets.map(w=>w.name),names);
 assert.deepEqual(n.widgets.map(w=>w.value),values);
 assert.equal(n.size[0],320);assert.equal(n.widgets[0].hidden,undefined);
}
console.log('PASS: independent foot/hand switches and ranges on new and legacy nodes; native values/order and loaded states preserved.');
