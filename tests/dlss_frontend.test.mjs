import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const app={registerExtension(extension){this.extension=extension;}};
globalThis.__dlssTestApp=app;
const source=(await fs.readFile(new URL('../web/dlss5.js',import.meta.url),'utf8'))
 .replace("import { app } from '../../scripts/app.js';",'const app=globalThis.__dlssTestApp;');
const {enhanceDlss}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const defaults={batch_mode:'independent_images',preview_mode:false,preview_long_edge:1024,processing_mode:'auto',
 preset:'原生默认',upscaling:'1x',show_advanced:false,compare_preview:false,model:'M',style:'默认',tone:1,
 structure:1.5,skin_structure:2,automatic_skin_mask:true,region_mode:'unified_lighting',person_strength:.35,
 background_strength:1,lighting_strength:.7,neutral_protection:.35,skin_protection:.6,edge_guard:.7,
 feather:6,mask_expand:0,temporal_mask_strength:.4,runtime_dir:'',release_comfy_models:true,
 worker_timeout:120,scene_change_threshold:.24,roi_x:0,roi_y:0,roi_width:1,roi_height:1};
const node={comfyClass:'LLDLSS5RegionEnhance',size:[360,500],inputs:[{name:'settings',link:null},{name:'person_mask',link:null}],
 widgets:Object.entries(defaults).map(([name,value])=>({name,value,type:typeof value==='boolean'?'toggle':typeof value==='number'?'number':'combo'})),
 computeSize(){return [360,50+this.widgets.reduce((h,w)=>h+(w.computeSize?.()[1]??24)+4,0)];},
 setSize(size){this.size=size;},setDirtyCanvas(){}};
const w=name=>node.widgets.find(widget=>widget.name===name);
const set=(name,value)=>{w(name).value=value;w(name).callback?.(value);};
const names=node.widgets.map(w=>w.name),initial=node.widgets.map(w=>w.value);
enhanceDlss(node);
assert.equal(w('structure').hidden,true);
assert.equal(w('roi_width').hidden,true);
assert.equal(w('preset').hidden,false);
assert.equal(w('preview_long_edge').hidden,true);
assert.deepEqual(node.widgets.map(w=>w.value),initial,'initial layout must not overwrite saved values');
const callback=w('show_advanced').callback;enhanceDlss(node);assert.equal(w('show_advanced').callback,callback);
const closedHeight=node.size[1];
set('show_advanced',true);
assert.equal(w('structure').hidden,false);
assert.equal(w('person_strength').hidden,true,'native mode hides unused regional controls');
assert.ok(node.size[1]>closedHeight);
set('processing_mode','regional');assert.equal(w('person_strength').hidden,false);
set('processing_mode','auto');
node.inputs[1].link=42;node.onConnectionsChange();assert.equal(w('person_strength').hidden,false);
node.inputs[1].link=null;node.onConnectionsChange();assert.equal(w('person_strength').hidden,true);
set('preset','环境增强');
assert.equal(w('structure').value,1.6);assert.equal(w('person_strength').value,.3);
assert.equal(w('person_strength').hidden,false);
set('person_strength',.15);
assert.equal(w('preset').value,'自定义');assert.equal(w('processing_mode').value,'regional');
assert.equal(w('person_strength').value,.15);
set('batch_mode','video_sequence');assert.equal(w('temporal_mask_strength').hidden,false);
set('batch_mode','independent_images');assert.equal(w('temporal_mask_strength').hidden,true);
set('show_advanced',false);assert.equal(w('person_strength').hidden,true);
assert.equal(w('person_strength').value,.15,'collapsing retains settings');
set('preview_mode',true);assert.equal(w('preview_long_edge').hidden,false);
set('compare_preview',true);assert.equal(w('roi_width').hidden,false);
node.inputs[0].link=77;node.onConnectionsChange();
assert.equal(w('preset').hidden,true,'legacy settings hide overridden inline fields');
assert.equal(w('compare_preview').hidden,undefined,'preview remains usable with legacy settings');
node.inputs[0].link=null;node.onConnectionsChange();assert.equal(w('preset').hidden,false);
app.extension.loadedGraphNode(node);
assert.deepEqual(node.widgets.map(w=>w.name),names);
assert.equal(w('person_strength').value,.15);
console.log('PASS: one-node defaults, inline presets, native/region adaptation, advanced/ROI toggles, legacy input priority, saved values and idempotent loading.');
