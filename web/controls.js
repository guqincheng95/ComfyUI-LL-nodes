// Standalone DOM controls; no framework or network dependencies.
export const LABELS = {
 exposure: '曝光（EV）', contrast: '对比度', highlights: '高光', shadows: '阴影',
 whites: '白色', blacks: '黑色', temperature: '色温（冷 → 暖）',
 tint: '色调（绿 → 洋红）', vibrance: '自然饱和度', saturation: '饱和度',
};
for (const [region, label] of [['shadow', '阴影'], ['midtone', '中间调'], ['highlight', '高光']]) {
 for (const [axis, colors] of [['cyan_red', '青 → 红'], ['magenta_green', '洋红 → 绿'], ['yellow_blue', '黄 → 蓝']]) {
  LABELS[`${region}_${axis}`] = `${label} · ${colors}`;
 }
}
// Color bars are UI direction hints; zero is neutral, with no change to processing.
export function gradientFor(name) {
 if(['exposure','contrast','highlights','shadows','whites','blacks'].includes(name))
  return 'linear-gradient(90deg, #080808 0%, #808080 50%, #ffffff 100%)';
 let ends;
 if(name==='temperature') ends=['#245adb','#df7815'];
 else if(name==='tint') ends=['#07843e','#b01aac'];
 else if(name.endsWith('cyan_red')) ends=['#0093a2','#c51d2e'];
 else if(name.endsWith('magenta_green')) ends=['#b01aac','#07843e'];
 else if(name.endsWith('yellow_blue')) ends=['#c9ab00','#245adb'];
 if(ends)return `linear-gradient(90deg, ${ends[0]} 0%, #ffffff 50%, ${ends[1]} 100%)`;
 return 'linear-gradient(90deg, #777777 0%, #ffffff 50%, transparent 100%), linear-gradient(0deg, #e23b5a 0%, #f1c93d 33%, #2cb76c 66%, #3d72df 100%)';
}
function ensureSliderStyles(doc) {
 if(!doc.head || doc.getElementById?.('ll-photo-slider-style'))return;
 const style=doc.createElement('style');style.id='ll-photo-slider-style';
 style.textContent=`
 .ll-photo-slider { appearance:none; -webkit-appearance:none; background:transparent; outline:none; }
 .ll-photo-slider::-webkit-slider-runnable-track { height:12px; background:transparent; border:0; }
 .ll-photo-slider::-webkit-slider-thumb { appearance:none; -webkit-appearance:none; width:16px; height:16px; margin-top:-2px; border:2px solid #222; border-radius:50%; background:#f4f4f4; box-shadow:0 0 0 1px #ddd; }
 .ll-photo-slider::-moz-range-track { height:12px; background:transparent; border:0; }
 .ll-photo-slider::-moz-range-progress { background:transparent; }
 .ll-photo-slider::-moz-range-thumb { width:12px; height:12px; border:2px solid #222; border-radius:50%; background:#f4f4f4; }
 .ll-photo-slider:focus-visible { outline:1px solid #7ec8e7; outline-offset:2px; }
 `;
 doc.head.append(style);
}
export const limitFor = name => name === 'exposure' ? 5 : 100;
export const fineStepFor = name => name === 'exposure' ? 0.05 : 1;
export function clampValue(value, limit) {
 const n = Number(value);
 return Number.isFinite(n) ? Math.max(-limit, Math.min(limit, n)) : 0;
}
export function snapValue(value, limit) {
 const n = clampValue(value, limit);
 return Math.sign(n) * Math.round(Math.abs(n) / (limit / 10)) * (limit / 10);
}
export function makeControl(name, initial, onChange, doc = document) {
 ensureSliderStyles(doc);
 const limit = limitFor(name), fine = fineStepFor(name);
 let value = clampValue(initial, limit);
 const root = doc.createElement('div');
 root.style.cssText = 'box-sizing:border-box;width:100%;height:62px;padding:3px 8px;color:#ddd;background:#282828;font:12px sans-serif;border-radius:6px;';
 const row = doc.createElement('div');
 row.style.cssText = 'display:flex;align-items:center;gap:5px;height:26px;';
 const label = doc.createElement('span'); label.textContent = LABELS[name];
 label.style.cssText = 'flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
 const number = doc.createElement('input'); number.type = 'number';
 number.min = -limit; number.max = limit; number.step = fine;
 number.setAttribute('aria-label', `${LABELS[name]}精确数值`);
 number.style.cssText = 'box-sizing:border-box;width:66px;height:24px;background:#191919;color:#fff;border:1px solid #666;border-radius:4px;text-align:center;appearance:textfield;';
 const minus = doc.createElement('button'), plus = doc.createElement('button');
 for (const [button, text, sign] of [[minus,'◀',-1],[plus,'▶',1]]) {
  button.type='button'; button.textContent=text;
  button.title=`${sign < 0 ? '减少' : '增加'} ${fine}`;
  button.setAttribute('aria-label', `${LABELS[name]}${button.title}`);
  button.style.cssText='width:25px;height:24px;padding:0;border:1px solid #666;border-radius:4px;background:#383838;color:#eee;cursor:pointer;';
  button.addEventListener('click', () => commit(Number((value+sign*fine).toFixed(6))));
 }
 row.append(label,minus,number,plus);
 const track = doc.createElement('div');
 track.style.cssText='position:relative;height:27px;display:flex;align-items:center;';
 const colorBar=doc.createElement('div');
 colorBar.style.cssText='position:absolute;left:8px;right:8px;top:8px;height:10px;border:1px solid #777;border-radius:5px;box-sizing:border-box;pointer-events:none;';
 colorBar.style.background=gradientFor(name);
 const ticks = doc.createElement('div');
 ticks.style.cssText='pointer-events:none;position:absolute;left:8px;right:8px;top:5px;height:18px;display:flex;justify-content:space-between;';
 for(let i=0;i<=20;i++) {
  const tick=doc.createElement('i');
  tick.style.cssText=`display:block;width:${i===10?2:1}px;height:${i===10?18:7}px;background:${i===10?'#111':'#333'};opacity:0.65;`;
  ticks.append(tick);
 }
 const slider=doc.createElement('input'); slider.type='range';
 slider.setAttribute('class','ll-photo-slider');
 // Fine-grained thumb position preserves old/off-grid values. Only user drags snap.
 slider.min=-limit; slider.max=limit; slider.step='any';
 slider.setAttribute('aria-label',`${LABELS[name]}滑块`);
 slider.title=`左负右正，各10档；每档 ${limit/10}；双击归零`;
 slider.style.cssText='position:relative;z-index:1;width:100%;height:20px;margin:0;background:transparent;cursor:pointer;';
 slider.addEventListener('input',()=>commit(snapValue(slider.value,limit)));
 slider.addEventListener('keydown',event=>{
  const delta={ArrowLeft:-1,ArrowDown:-1,ArrowRight:1,ArrowUp:1}[event.key];
  if(delta){event.preventDefault();commit(snapValue(value,limit)+delta*limit/10);}
  else if(event.key==='Home'||event.key==='End'){event.preventDefault();commit(event.key==='Home'?-limit:limit);}
 });
 slider.addEventListener('dblclick',()=>commit(0));
 number.addEventListener('change',()=>{
  if(number.value.trim()===''||!Number.isFinite(number.valueAsNumber)){render();return;}
  commit(number.valueAsNumber);
 });
 number.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();number.blur();}});
 track.append(colorBar,ticks,slider); root.append(row,track);
 for(const event of ['pointerdown','mousedown','keydown','dblclick']) root.addEventListener(event,e=>e.stopPropagation());
 function render(){
  slider.value=String(value);
  slider.setAttribute('aria-valuetext',String(value));
  if(doc.activeElement!==number) number.value=String(value);
 }
 function commit(next){value=clampValue(next,limit);render();onChange(value);}
 render();
 return {element:root,slider,number,minus,plus,
  get value(){return value;},
  setValue(next){value=clampValue(next,limit);render();},
  setDisabled(disabled){for(const element of [slider,number,minus,plus]) element.disabled=disabled;root.style.opacity=disabled?'0.5':'1';},
 };
}
