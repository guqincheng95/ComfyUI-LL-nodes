import { createPhotoRenderer } from './photo_preview_gl.js';

const MAX_SIDE=640;

export async function decodePreview(data) {
  const {width,height,pixels}=data;
  if(data.version!==1 || !Number.isInteger(width) || !Number.isInteger(height)
    || Math.min(width,height)<1 || Math.max(width,height)>MAX_SIDE
    || typeof pixels!=='string' || pixels.length>4_500_000)throw Error('预览数据无效');
  const compressed=Uint8Array.from(atob(pixels),char=>char.charCodeAt(0));
  const reader=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('deflate')).getReader();
  const output=new Uint8Array(width*height*8);
  let offset=0;
  try {
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      if(offset+value.length>output.length){await reader.cancel();throw Error('预览图大小无效');}
      output.set(value,offset);offset+=value.length;
    }
  } finally { reader.releaseLock(); }
  if(offset!==output.length)throw Error('预览图不完整');
  const view=new DataView(output.buffer);
  const rgba=new Uint16Array(output.length/2);
  for(let i=0;i<rgba.length;i++)rgba[i]=view.getUint16(i*2,true);
  return rgba;
}

export function installPhotoPreview(node,{records,nodeWidth,syncWidth,resize}) {
  const toggle=node.widgets.find(w=>w.name==='live_preview');
  if(!toggle)return null;
  const root=document.createElement('div');
  root.style.cssText='box-sizing:border-box;width:100%;height:100%;min-width:0;padding:3px 10px 0;color:#ddd;font:12px/18px sans-serif;overflow:hidden;';
  const bar=document.createElement('div');
  bar.style.cssText='display:flex;gap:6px;align-items:center;justify-content:space-between;height:25px;min-width:0;';
  const status=document.createElement('span');
  status.setAttribute('role','status');
  status.style.cssText='min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
  const compare=document.createElement('button');
  compare.type='button';compare.textContent='看校正底图';compare.disabled=true;
  compare.style.cssText='box-sizing:border-box;flex:0 0 auto;max-width:48%;min-width:0;height:23px;min-height:0;margin:0;padding:0 5px;color:#eee;background:#34434a;border:1px solid #5c737d;border-radius:4px;font:inherit;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
  bar.append(status,compare);
  const canvas=document.createElement('canvas');
  canvas.setAttribute('aria-label','后期实时预览');
  canvas.style.cssText='display:none;width:100%;height:calc(100% - 25px);object-fit:contain;background:#202020;';
  root.append(bar,canvas);
  for(const event of ['pointerdown','mousedown','keydown'])compare.addEventListener(event,e=>e.stopPropagation());

  let frame=null, renderer=null, handle=0, generation=0, disposed=false, showingBase=false;
  let observedEnabled=false, stale=false, signature='', lastDraw='', message='';
  let widget;
  const linked=name=>node.inputs?.some(input=>(input.widget?.name??input.name)===name && input.link!=null);
  const enabled=()=>Boolean(toggle.value) || linked('live_preview');
  const height=()=>!enabled()?0:frame?Math.min(310,Math.round(nodeWidth()*.92))+28:30;
  const getWidget=name=>node.widgets.find(w=>w.name===name);
  const autoKeys=node.comfyClass==='LLPortraitColorAlign'
    ? ['skin_source','white_balance_strength','face_strength','body_strength','skin_luminance']
    : ['auto_mode','match_strength','match_luminance','match_color'];
  const links=()=>JSON.stringify((node.inputs??[]).map(x=>[x.widget?.name??x.name,x.link??null]));
  function draw(){
    handle=0;
    if(!frame || !renderer || disposed || !observedEnabled)return;
    const manual=Object.fromEntries(records.map(({original})=>
      [original.name,linked(original.name)?frame.manual?.[original.name]:original.value]));
    const key=JSON.stringify([manual,showingBase]);
    if(key===lastDraw)return;
    renderer.draw(manual,showingBase);lastDraw=key;
  }
  function poll(){
    if(disposed||!widget)return;
    syncWidth(widget);
    const active=enabled();
    if(active!==observedEnabled){
      observedEnabled=active;
      widget.hidden=!active;widget.type=active?'ll_photo_preview':'hidden';
      root.style.display=active?'block':'none';
      if(!active){generation++;frame=null;message='';renderer?.dispose();renderer=null;canvas.style.display='none';}
      resize();
    }
    if(!active)return;
    const old=stale;
    stale=Boolean(frame && (signature!==links() || autoKeys.some(name=>{
      const value=getWidget(name)?.value;
      const expected=frame.automatic?.[name];
      if(linked(name)||value===undefined||expected===undefined)return false;
      return typeof expected==='number'?Math.abs(Number(value)-expected)>1e-6:value!==expected;
    })));
    if(stale!==old)node.setDirtyCanvas?.(true,true);
    const label=message || (!frame?'运行一次以载入预览':stale?'自动设置或接线已变，请重新运行'
      : showingBase?'校正底图':frame.batch>1?'实时预览 · 批次首张':'实时预览');
    if(status.textContent!==label){status.textContent=label;status.title=label;}
    compare.disabled=!frame;
    if(frame&&!handle)handle=requestAnimationFrame(draw);
  }
  compare.addEventListener('click',()=>{
    showingBase=!showingBase;compare.setAttribute('aria-pressed',String(showingBase));
    compare.textContent=showingBase?'看手动效果':'看校正底图';poll();
  });
  const previous=toggle.callback;
  toggle.callback=function(...args){const result=previous?.apply(this,args);poll();return result;};
  widget=node.addDOMWidget('ll_photo_preview_panel','ll_photo_preview',root,{
    serialize:false,hideOnZoom:true,margin:0,
    getMinHeight:height,getMaxHeight:height,
    afterResize:()=>{if(widget)syncWidth(widget);},
    onDraw:poll,
  });
  widget.hidden=true;widget.type='hidden';root.style.display='none';
  widget.computeSize=()=>[nodeWidth(),widget.hidden?-4:height()];

  async function receive(data) {
    if(!enabled()||disposed)return;
    const token=++generation;
    const inputSignature=links();
    message='正在载入预览…';poll();
    try {
      const rgba=await decodePreview(data);
      if(disposed||!enabled()||token!==generation)return;
      renderer??=createPhotoRenderer(canvas);
      renderer.upload(data.width,data.height,rgba);
      frame={manual:data.manual,automatic:data.automatic,batch:data.batch};
      signature=inputSignature;lastDraw='';message='';canvas.style.display='block';
      resize();poll();
    } catch {
      if(disposed||token!==generation)return;
      frame=null;renderer?.dispose();renderer=null;canvas.style.display='none';
      message='实时预览不可用，可接「预览图像」';
      resize();poll();
    }
  }
  canvas.addEventListener('webglcontextlost',event=>{
    event.preventDefault();
    generation++;frame=null;renderer=null;canvas.style.display='none';message='预览已暂停，请重新运行';
    resize();poll();
  });
  const onExecuted=node.onExecuted, onRemoved=node.onRemoved;
  node.onExecuted=function(output,...rest){
    const result=onExecuted?.call(this,output,...rest);
    const data=output?.ll_photo_preview?.[0];
    if(data)void receive(data);
    return result;
  };
  node.onRemoved=function(...args){
    disposed=true;generation++;if(handle)cancelAnimationFrame(handle);
    renderer?.dispose();renderer=null;frame=null;
    return onRemoved?.apply(this,args);
  };
  poll();
  return {poll,widget};
}
