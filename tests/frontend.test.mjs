// Dependency-free DOM/Comfy adapter harness, NOT an actual ComfyUI browser test.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { LABELS, makeControl, limitFor, gradientFor } from '../web/controls.js';
class Element {
 constructor(){this.style={};this.children=[];this.events={};this.value='';this.disabled=false;}
 append(...children){this.children.push(...children);}
 setAttribute(key,value){this[key]=value;}
 addEventListener(type,callback){(this.events[type]??=[]).push(callback);}
 emit(type,props={}){const e={preventDefault(){},stopPropagation(){},...props};for(const fn of this.events[type]||[])fn(e);}
 get valueAsNumber(){return Number(this.value);}
 blur(){document.activeElement=null;this.emit('change');}
}
globalThis.document={createElement:()=>new Element(),activeElement:null};
assert.ok(gradientFor('exposure').includes('#808080 50%'));
for(const name of Object.keys(LABELS).filter(n=>!['exposure','contrast','highlights','shadows','whites','blacks'].includes(n)))assert.ok(gradientFor(name).includes('#ffffff 50%'));
assert.ok(gradientFor('temperature').includes('#245adb'));
assert.ok(gradientFor('shadow_cyan_red').includes('#0093a2'));
let cases=0;
for(const name of Object.keys(LABELS)){
 let output;const control=makeControl(name,0,v=>output=v);const limit=limitFor(name);
 for(let i=-10;i<=10;i++){
  control.slider.value=String(i*limit/10);control.slider.emit('input');
  assert.equal(output,i*limit/10);cases++;
 }
 control.slider.value=String(-limit*0.16);control.slider.emit('input');assert.equal(output,-limit*0.2);
 control.slider.value=String(limit*0.16);control.slider.emit('input');assert.equal(output,limit*0.2);
 control.setValue(0);control.plus.emit('click');assert.equal(output,name==='exposure'?0.05:1);
 control.minus.emit('click');assert.equal(output,0);
 control.setValue(name==='exposure'?0.3:-6);assert.equal(control.value,name==='exposure'?0.3:-6);
 control.number.value=String(name==='exposure'?0.37:-6.3);control.number.emit('change');assert.equal(output,name==='exposure'?0.37:-6.3);
 control.number.value='';control.number.emit('change');assert.equal(control.value,output);
 control.slider.emit('keydown',{key:'Home'});assert.equal(output,-limit);
 control.slider.emit('keydown',{key:'ArrowRight'});assert.equal(output,-limit+limit/10);
 control.slider.emit('keydown',{key:'End'});assert.equal(output,limit);
 control.slider.emit('dblclick');assert.equal(output,0);
 control.setDisabled(true);assert.ok(control.slider.disabled && control.plus.disabled);
}
const source=(await fs.readFile(new URL('../web/photo_finish.js',import.meta.url),'utf8'))
 .replace("import { app } from '../../scripts/app.js';",'const app = globalThis.testApp;')
 .replace("'./controls.js'",JSON.stringify(new URL('../web/controls.js',import.meta.url).href));
globalThis.testApp={canvas:{},registerExtension(extension){this.extension=extension;}};
const {enhanceNode}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const names=Object.keys(LABELS);
function makeNode(){return {
 comfyClass:'AIVisualPhotoFinish',size:[300,500],inputs:[],
 widgets:[...names.map(name=>({name,value:name==='exposure'?0.3:-6,options:{}})),{name:'preserve_luminosity',value:true}],
 computeSize(){return [360,1350];},setSize(s){this.size=s;},
 addDOMWidget(name,type,element,options){
  assert.ok(!this.widgets.some(w=>w.name===name),'duplicate widget registration');
  const w={name,type,element,options,get value(){return options.getValue();},set value(v){options.setValue(v);}};this.widgets.push(w);return w;
 }
};}
const node=makeNode(),before=node.widgets.map(w=>({name:w.name,value:w.value}));
enhanceNode(node);enhanceNode(node);
assert.deepEqual(node.widgets.map(w=>({name:w.name,value:w.value})),before);
const saved=node.widgets.map(w=>w.serializeValue?w.serializeValue():w.value);
const restored=makeNode();enhanceNode(restored);saved.forEach((v,i)=>restored.widgets[i].value=v);
assert.deepEqual(restored.widgets.map(w=>w.value),saved);
restored.widgets[0].value=1.25;assert.equal(node.widgets[0].value,0.3);
node.inputs=[{widget:{name:'exposure'},link:12}];node.widgets[0].options.onDraw();
assert.ok(node.__photoFinishUI.controls.get('exposure').slider.disabled);
assert.equal(node.__photoFinishUI.groups.size,3);
assert.equal(node.widgets[1].hidden,true);
const exposureHeader=node.__photoFinishUI.records.find(r=>r.original.name==='exposure').header;
exposureHeader.emit('click');assert.equal(node.widgets[1].hidden,false);
assert.equal(node.properties.llPhotoSections.exposure,true);
const savedProperties=JSON.parse(JSON.stringify(node.properties));
const savedValues=node.widgets.map(w=>w.value);
exposureHeader.emit('click');assert.equal(node.widgets[1].hidden,true);
assert.deepEqual(node.widgets.map(w=>w.value),savedValues);
restored.properties=savedProperties;testApp.extension.loadedGraphNode(restored);
assert.equal(restored.widgets[1].hidden,false);
assert.equal(restored.widgets.length,20);
assert.equal(restored.widgets[19].value,true);
console.log(`PASS: ${names.length} controls / ${cases} signed positions; snapping; fine buttons; numeric input; keyboard; reset; connected disabling; old value/order preservation; save/reload; independent nodes; idempotence; three sections; collapsed values and restored states; boolean; neutral-centered gradient directions.`);
