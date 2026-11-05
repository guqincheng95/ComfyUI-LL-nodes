// Real Chromium layout checks with ComfyUI's DOM overlay sizing contract.
// This adapter does not run a full ComfyUI server or Vue renderer.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {deflateSync} from 'node:zlib';
const { chromium } = await import(process.env.LL_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader']});
const page = await browser.newPage({viewport:{width:1500,height:1000}});
const errors=[];
page.on('pageerror',error=>errors.push(String(error)));
await page.route('http://photo.test/**',async route=>{
 const path=new URL(route.request().url()).pathname;
 if(path==='/scripts/app.js')return route.fulfill({contentType:'application/javascript',body:'export const app={canvas:{},registerExtension(e){window.extension=e;}};'});
 if(path.endsWith('.js'))return route.fulfill({contentType:'application/javascript',body:await fs.readFile(new URL('../web/'+path.split('/').pop(),import.meta.url),'utf8')});
 return route.fulfill({contentType:'text/html; charset=utf-8',body:`<meta charset="utf-8"><style>
 body{margin:0;background:#222;color:#eee;font:12px sans-serif}
 #node{position:absolute;left:30px;top:30px;background:#444;transform-origin:0 0}
 .dom-widget{position:absolute}button,input{font:inherit}
 </style><div id="node"></div><script type="module" src="/extensions/ll/photo_finish.js"></script>`});
});
try {
 await page.goto('http://photo.test/');
 await page.waitForFunction(()=>window.extension);
 await page.evaluate(async()=>{
  const {LABELS}=await import('/extensions/ll/controls.js');
  window.makeNode=(comfyClass='AIVisualPhotoFinish',live=false)=>{
   const nodeElement=document.querySelector('#node');nodeElement.replaceChildren();
   const n={comfyClass,size:[360,500],properties:{},inputs:[],widgets:[
    ...Object.keys(LABELS).map(name=>({name,value:name==='exposure'?.3:0,options:{}})),
    {name:'preserve_luminosity',value:true,options:{}},
    ...['auto_mode','match_strength','match_luminance','match_color'].map((name,i)=>({name,value:i?1:'off',options:{}})),
   ],graph:{beforeChange(){},afterChange(){}},
   computeSize(){return [280,54+this.widgets.reduce((sum,w)=>sum+(w.computeSize?.(this.size[0])[1]??24)+4,0)];},
   setSize(size){this.size=size;for(const w of this.widgets)w.options?.afterResize?.();this.layout?.();},
   setDirtyCanvas(){this.layout?.();},
   addDOMWidget(name,type,element,options){
    const host=document.createElement('div');host.className='dom-widget';host.append(element);nodeElement.append(host);
    const w={name,type,element,host,options,width:150,get value(){return options.getValue();},set value(v){options.setValue(v);}};
    this.widgets.push(w);return w;
   },
   layout(){
    nodeElement.style.width=this.size[0]+'px';nodeElement.style.height=this.size[1]+'px';
    let y=40;
    for(const w of this.widgets){
     const h=(w.computeSize?.(this.size[0])[1]??24)+4;
     if(w.host){
      // Canvas DOMWidgets.vue: position += margin; size -= margin * 2.
      const margin=w.options.margin??10;
      const visible=!w.hidden && w.type!=='hidden';
      Object.assign(w.host.style,{display:visible?'block':'none',left:margin+'px',top:(y+margin)+'px',width:((w.width??this.size[0])-2*margin)+'px',height:Math.max(0,h-2*margin)+'px'});
     }
     y+=h;
    }
   }};
   if(live)n.widgets.push({name:'live_preview',value:false,options:{}});
   extension.nodeCreated(n);n.layout();return n;
  };
  window.n=makeNode();
  window.layoutErrors=()=>{
   const failures=[],frame=document.querySelector('#node').getBoundingClientRect();
   for(const r of n.__photoFinishUI.records){
    if(r.widget.hidden)continue;
    const host=r.widget.host.getBoundingClientRect();
    if(Math.abs(host.width-frame.width)>1)failures.push({name:r.original.name,hostWidth:host.width,nodeWidth:frame.width});
    const items=[r.element,...r.element.querySelectorAll('button,input')];
    for(const element of items){
     if(!element.getClientRects().length)continue;
     const b=element.getBoundingClientRect();
     if(b.left<host.left-1 || b.right>host.right+1 || b.top<host.top-1 || b.bottom>host.bottom+1 || b.left<frame.left-1 || b.right>frame.right+1 || b.bottom>frame.bottom+1)
      failures.push({name:r.original.name,tag:element.tagName,host:[host.width,host.height],bounds:[b.width,b.height],bottomOverflow:b.bottom-host.bottom});
    }
    // Catch overflow hidden by a clipping rule, rather than accepting cut-off controls.
    const control=r.control.element;
    if(control.getClientRects().length && (control.scrollHeight>control.clientHeight+1 || control.scrollWidth>control.clientWidth+1))failures.push({name:r.original.name,clipped:true});
   }
   return failures;
  };
 });
 const initialValues=await page.evaluate(()=>n.widgets.map(w=>w.value));
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],'collapsed headers must fit their allocated slots');
 let layouts=0;
 for(const width of [210,280,360,640]){
  for(const scale of [.5,1,1.75]){
   for(const open of [false,true]){
    await page.evaluate(({width,scale,open})=>{
     n.size[0]=width;
     n.properties.llPhotoSections={exposure:open,temperature:open,color:open};
     n.__photoFinishUI.refresh();n.__photoFinishUI.resize();
     document.querySelector('#node').style.transform=`scale(${scale})`;
    },{width,scale,open});
    assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],`width=${width}, scale=${scale}, open=${open}`);
    assert.equal(await page.getByRole('slider').count(),open?19:0);
    if(open){
     const slider=page.getByRole('slider',{name:'对比度滑块',exact:true});
     const box=await slider.boundingBox();
     // The 16px thumb center travels between the inset endpoints.
     await page.mouse.click(box.x+box.width*.75-4*scale,box.y+box.height*.5);
     assert.equal(await page.getByRole('spinbutton',{name:'对比度精确数值',exact:true}).inputValue(),'50','pointer must track the scaled slider');
     await page.evaluate(()=>n.widgets.find(w=>w.name==='contrast').value=0);
    }
    assert.deepEqual(await page.evaluate(()=>n.widgets.map(w=>w.value)),initialValues);
    layouts++;
   }
  }
 }
 // Simulate a live width drag on an already-open node; it must not need a toggle.
 await page.evaluate(()=>{n.setSize([480,n.size[1]]);});
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],'live width resize must fill the node');
 // Some canvas paths update the node width before notifying DOM overlays.
 await page.evaluate(()=>{n.size[0]=310;for(const w of n.widgets)w.options?.onDraw?.();n.layout();});
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],'canvas draw must refresh stale widget widths');
 // Do not enlarge a manually narrowed node each time a section opens/closes.
 await page.evaluate(()=>{n.size[0]=280;n.__photoFinishUI.resize();});
 assert.equal(await page.evaluate(()=>n.size[0]),280);
 await page.evaluate(()=>document.querySelector('#node').style.transform='scale(1)');
 await page.getByRole('button',{name:'曝光（EV）增加 0.05',exact:true}).click();
 assert.equal(await page.getByRole('spinbutton',{name:'曝光（EV）精确数值',exact:true}).inputValue(),'0.35');
 // Legacy frontends use type=hidden; modern ones also consult widget.hidden.
 await page.getByRole('button',{name:'曝光折叠区域',exact:true}).click();
 assert.equal(await page.evaluate(()=>n.widgets[1].type),'hidden');
 assert.equal(await page.evaluate(()=>n.widgets[0].serializeValue()),.35);
 const saved=await page.evaluate(()=>({properties:structuredClone(n.properties),values:n.widgets.map(w=>w.value),size:[...n.size]}));
 await page.evaluate(saved=>{n=makeNode();n.properties=saved.properties;n.size=saved.size;saved.values.forEach((v,i)=>n.widgets[i].value=v);extension.loadedGraphNode(n);},saved);
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[]);
 assert.deepEqual(await page.evaluate(()=>n.widgets.map(w=>w.value)),saved.values);
 const fixture=JSON.parse(await fs.readFile(new URL('./photo_preview_fixture.json',import.meta.url),'utf8'));
 const pixelError=await page.evaluate(async fixture=>{
  const {createPhotoRenderer}=await import('/extensions/ll/photo_preview_gl.js');
  const canvas=document.createElement('canvas');
  const renderer=createPhotoRenderer(canvas,{preserveDrawingBuffer:true});
  renderer.upload(fixture.width,fixture.height,new Uint16Array(fixture.rgba16));
  const gl=canvas.getContext('webgl2');
  const actual=new Uint8Array(fixture.width*fixture.height*4);
  let max=0;
  for(const {params,rgba8} of fixture.cases){
   renderer.draw(params);
   gl.readPixels(0,0,fixture.width,fixture.height,gl.RGBA,gl.UNSIGNED_BYTE,actual);
   for(let y=0;y<fixture.height;y++)for(let x=0;x<fixture.width*4;x++)
    max=Math.max(max,Math.abs(actual[(fixture.height-1-y)*fixture.width*4+x]-rgba8[y*fixture.width*4+x]));
  }
  renderer.dispose();
  return max;
 },fixture);
 assert.ok(pixelError<=1,`GPU and Python color fixtures diverged: ${pixelError}/255`);
 // Preserve the test framebuffer so we can read after animation frames.
 await page.evaluate(()=>{
  const get=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(type,options){
   return get.call(this,type,type==='webgl2'?{...options,preserveDrawingBuffer:true}:options);
  };
 });
 const bytes=Buffer.alloc(fixture.rgba16.length*2);
 fixture.rgba16.forEach((value,i)=>bytes.writeUInt16LE(value,i*2));
 const payload={version:1,width:fixture.width,height:fixture.height,batch:2,manual:{},automatic:{auto_mode:'off'},pixels:deflateSync(bytes).toString('base64')};
 for(const nodeClass of ['AIVisualPhotoFinish','LLPortraitColorAlign']){
  await page.evaluate(nodeClass=>{n=makeNode(nodeClass,true);n.properties.llPhotoSections={exposure:true};n.__photoFinishUI.refresh();n.__photoFinishUI.resize();},nodeClass);
  assert.equal(await page.getByRole('status').isVisible(),false);
  await page.evaluate(payload=>{
   const toggle=n.widgets.find(w=>w.name==='live_preview');toggle.value=true;toggle.callback();
   n.onExecuted({ll_photo_preview:[payload]});
  },payload);
  await page.getByText('实时预览 · 批次首张',{exact:true}).waitFor();
  const preview=page.getByLabel('后期实时预览',{exact:true});
  const rendered=()=>preview.evaluate(canvas=>canvas.toDataURL());
  const first=await rendered();
  await page.getByRole('button',{name:'曝光（EV）增加 0.05',exact:true}).click();
  await page.waitForFunction(first=>document.querySelector('canvas').toDataURL()!==first,first);
  await page.getByRole('button',{name:'看校正底图',exact:true}).click();
  await page.getByText('校正底图',{exact:true}).waitFor();
  await page.evaluate(()=>{n.setSize([220,n.size[1]]);n.__photoFinishUI.resize();});
  assert.deepEqual(await page.evaluate(()=>layoutErrors()),[]);
  const widths=await page.evaluate(()=>[n.size[0],n.__photoFinishUI.preview.widget.host.getBoundingClientRect().width]);
  assert.deepEqual(widths,[220,220]);
  await page.evaluate(()=>{n.inputs.push({name:'image',link:3});n.__photoFinishUI.preview.poll();});
  await page.getByText('自动设置或接线已变，请重新运行',{exact:true}).waitFor();
  await page.evaluate(()=>{const toggle=n.widgets.find(w=>w.name==='live_preview');toggle.value=false;toggle.callback();});
  assert.equal(await preview.isVisible(),false);
 }
 // Shared theme rules must not grow the controls beyond the reported height.
 await page.addStyleTag({content:'button,input{min-width:100px;min-height:36px;padding:8px;margin:4px}'});
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],'theme sizing must not override control dimensions');
 assert.deepEqual(errors,[]);
 console.log(`PASS: live preview on both nodes; Python color parity max ${pixelError}/255; slider redraw, comparison, narrow layout and stale-data state.`);
 console.log(JSON.stringify({browser:browser.version(),layouts,checks:'allocated DOM bounds; full node width with stale 150px widget size; live resize; no clipped controls; narrow/normal/wide; canvas zoom and pointer tracking; collapse; exact buttons; hidden compatibility; save/reload; theme sizing',errors}));
} finally {await browser.close();}

// Check the ratio node color controls in the same browser regression job.
await import("./aspect_color.browser.mjs");
