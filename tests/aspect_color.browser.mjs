import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const { chromium } = await import(process.env.LL_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(String(error)));
const source = await fs.readFile(new URL('../web/aspect_color.js', import.meta.url), 'utf8');
await page.route('http://aspect.test/**', route => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/scripts/app.js') return route.fulfill({contentType:'application/javascript',
    body:'export const app={canvas:{},registerExtension(e){window.extension=e;}};'});
  if (path.endsWith('.js')) return route.fulfill({contentType:'application/javascript',body:source});
  return route.fulfill({contentType:'text/html; charset=utf-8',
    body:'<meta charset="utf-8"><main style="width:230px"></main><script type="module" src="/extensions/ll/aspect_color.js"></script>'});
});

try {
  await page.goto('http://aspect.test/');
  await page.waitForFunction(() => window.extension);
  await page.evaluate(() => {
    window.calls = [];
    window.EyeDropper = class {
      open({signal}) {
        if (!navigator.userActivation.isActive) throw new Error('Missing user activation');
        if (window.cancelPick) return Promise.reject(new DOMException('Esc','AbortError'));
        if (window.deferPick) return new Promise((resolve,reject) => {
          window.finishPick = resolve;
          signal.addEventListener('abort', () => reject(new DOMException('Removed','AbortError')), {once:true});
        });
        return Promise.resolve({sRGBHex:'#FAFAFA'});
      }
    };
    window.makeNode = saved => {
      document.querySelector('main').replaceChildren();
      const names = ['aspect_ratio','proportional_width','proportional_height','fit','method',
        'round_to_multiple','scale_to_side','scale_to_length','background_color','flip_ratio','rounding','mask_method'];
      const values = saved || ['9:16',9,16,'letterbox','lanczos',8,'longest',1280,'#000000',false,'nearest','same'];
      const n = {comfyClass:'LLImageAspectScale',size:[230,290],inputs:[],
        widgets:names.map((name,i) => ({name,value:values[i],options:{}})),
        graph:{beforeChange(){calls.push('before');},afterChange(){calls.push('after');}},
        setDirtyCanvas(){},computeSize(){return [230,298];},setSize(size){this.size=size;},
        addDOMWidget(name,type,element,options){
          document.querySelector('main').append(element);
          const w={name,type,element,options,get value(){return options.getValue();},
            set value(v){options.setValue(v);this.callback?.(this.value);}};
          this.widgets.push(w);
          return w;
        }};
      n.widgets[8].callback = color => calls.push(color);
      extension.nodeCreated(n);
      extension.loadedGraphNode(n);
      return n;
    };
    window.n = makeNode();
  });
  const eyedropper = page.getByRole('button',{name:'屏幕取色',exact:true});
  const hex = page.getByRole('textbox',{name:'补边颜色编码',exact:true});
  const saved = () => page.evaluate(() => n.widgets.map(w => w.serializeValue?.() ?? w.value));

  await eyedropper.click();
  assert.equal(await hex.inputValue(),'#fafafa');
  assert.deepEqual(await page.evaluate(() => calls),['before','#fafafa','after']);
  assert.deepEqual(await saved(),['9:16',9,16,'letterbox','lanczos',8,'longest',1280,'#fafafa',false,'nearest','same']);
  await page.evaluate(() => {window.cancelPick=true;});
  await eyedropper.click();
  assert.equal(await hex.inputValue(),'#fafafa');
  assert.equal(await page.evaluate(() => calls.length),3);
  await page.evaluate(() => {window.cancelPick=false;window.deferPick=true;});
  await eyedropper.click();
  await page.waitForFunction(() => Boolean(window.finishPick));
  assert.equal(await eyedropper.isDisabled(),true);
  await hex.fill('#123456');
  await hex.press('Enter');
  await page.evaluate(() => {window.finishPick({sRGBHex:'#ffffff'});window.deferPick=false;});
  await page.waitForFunction(() => !document.querySelector('button').disabled);
  assert.equal(await hex.inputValue(),'#123456','late pick must not overwrite a newer edit');
  await hex.fill('#oops');
  await hex.press('Enter');
  assert.equal(await hex.inputValue(),'#123456');

  await page.evaluate(() => {
    window.EyeDropper=undefined;
    n.__llAspectColor.refresh();
  });
  assert.equal(await eyedropper.isDisabled(),true);
  await page.locator('input[type=color]').evaluate(el => {
    el.value='#eeeeee';
    el.dispatchEvent(new Event('change',{bubbles:true}));
  });
  assert.equal(await hex.inputValue(),'#eeeeee');
  const values = await saved();
  await page.evaluate(values => { n=makeNode(values); }, values);
  assert.deepEqual(await saved(),values);
  assert.equal(await page.locator('input[type=color]').inputValue(),'#eeeeee');
  await page.evaluate(() => {
    n.inputs=[{name:'background_color',link:4}];
    n.widgets[8].options.onDraw();
  });
  assert.equal(await hex.isDisabled(),true);
  assert.equal(await page.locator('input[type=color]').isDisabled(),true);
  assert.equal(await page.evaluate(() => {
    const row=document.querySelector('main > div');
    const rect=row.getBoundingClientRect();
    return row.scrollWidth===row.clientWidth && [...row.querySelectorAll('input,button')].every(el => {
      const item=el.getBoundingClientRect();
      return item.top>=rect.top && item.bottom<=rect.bottom && item.left>=rect.left && item.right<=rect.right;
    });
  }),true,'controls must fit a 230 px node');
  assert.deepEqual(errors,[]);
  console.log('PASS: padding eyedropper selection/cancel, stale pick, color picker fallback, HEX validation, linked input, serialized order and narrow layout.');
} finally {
  await browser.close();
}
