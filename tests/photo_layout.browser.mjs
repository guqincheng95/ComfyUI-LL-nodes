// Real Chromium layout checks with ComfyUI's DOM overlay sizing contract.
// This adapter does not run a full ComfyUI server or Vue renderer.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const { chromium } = await import(process.env.LL_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
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
  window.makeNode=()=>{
   const nodeElement=document.querySelector('#node');nodeElement.replaceChildren();
   const n={comfyClass:'AIVisualPhotoFinish',size:[360,500],properties:{},inputs:[],widgets:[
    ...Object.keys(LABELS).map(name=>({name,value:name==='exposure'?.3:0,options:{}})),
    {name:'preserve_luminosity',value:true,options:{}},
    ...['auto_mode','match_strength','match_luminance','match_color'].map((name,i)=>({name,value:i?1:'off',options:{}})),
   ],graph:{beforeChange(){},afterChange(){}},
   computeSize(){return [280,54+this.widgets.reduce((sum,w)=>sum+(w.computeSize?.(this.size[0])[1]??24)+4,0)];},
   setSize(size){this.size=size;this.layout?.();},
   setDirtyCanvas(){this.layout?.();},
   addDOMWidget(name,type,element,options){
    const host=document.createElement('div');host.className='dom-widget';host.append(element);nodeElement.append(host);
    const w={name,type,element,host,options,get value(){return options.getValue();},set value(v){options.setValue(v);}};
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
      Object.assign(w.host.style,{display:visible?'block':'none',left:margin+'px',top:(y+margin)+'px',width:(this.size[0]-2*margin)+'px',height:Math.max(0,h-2*margin)+'px'});
     }
     y+=h;
    }
   }};
   extension.nodeCreated(n);n.layout();return n;
  };
  window.n=makeNode();
  window.layoutErrors=()=>{
   const failures=[],frame=document.querySelector('#node').getBoundingClientRect();
   for(const r of n.__photoFinishUI.records){
    if(r.widget.hidden)continue;
    const host=r.widget.host.getBoundingClientRect();
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
 for(const width of [280,360,640]){
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
     await page.mouse.click(box.x+box.width*.75,box.y+box.height*.5);
     assert.equal(await page.getByRole('spinbutton',{name:'对比度精确数值',exact:true}).inputValue(),'50','pointer must track the scaled slider');
     await page.evaluate(()=>n.widgets.find(w=>w.name==='contrast').value=0);
    }
    assert.deepEqual(await page.evaluate(()=>n.widgets.map(w=>w.value)),initialValues);
    layouts++;
   }
  }
 }
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
 // Shared theme rules must not grow the controls beyond the reported height.
 await page.addStyleTag({content:'button,input{min-width:100px;min-height:36px;padding:8px;margin:4px}'});
 assert.deepEqual(await page.evaluate(()=>layoutErrors()),[],'theme sizing must not override control dimensions');
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({browser:browser.version(),layouts,checks:'allocated DOM bounds; whole node bounds; no clipped controls; narrow/normal/wide; canvas zoom and pointer tracking; collapse; exact buttons; hidden compatibility; save/reload; theme sizing',errors}));
} finally {await browser.close();}
