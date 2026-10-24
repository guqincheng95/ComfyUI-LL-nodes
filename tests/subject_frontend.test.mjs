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
