import { app } from '../../scripts/app.js';

const FIELD = 'background_color';
const HEX = /^#[0-9a-f]{6}$/i;
const ROW_HEIGHT = 28;

export function enhanceAspectColor(node) {
  if (node.comfyClass !== 'LLImageAspectScale' || node.__llAspectColor
      || typeof node.addDOMWidget !== 'function') return;
  const original = node.widgets?.find(widget => widget.name === FIELD);
  if (!original) return;
  const index = node.widgets.indexOf(original);
  const linked = () => Boolean(node.inputs?.some(input =>
    (input.name === FIELD || input.widget?.name === FIELD) && input.link != null));
  const supported = () => typeof globalThis.EyeDropper === 'function';

  const row = document.createElement('div');
  row.style.cssText = 'display:flex;align-items:center;gap:5px;width:100%;height:28px;padding:0 10px;box-sizing:border-box;min-width:0;overflow:hidden;color:var(--input-text,#ddd);font:12px sans-serif;';
  const label = document.createElement('span');
  label.textContent = '补边颜色';
  label.title = '仅在等比补边时使用';
  label.style.cssText = 'flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
  const swatch = document.createElement('input');
  swatch.type = 'color';
  swatch.setAttribute('aria-label', '补边颜色调色盘');
  swatch.title = '打开调色盘';
  swatch.style.cssText = 'box-sizing:border-box;flex:0 0 27px;width:27px;min-width:0;height:24px;padding:1px;margin:0;border:1px solid #777;border-radius:4px;background:transparent;cursor:pointer;';
  const hex = document.createElement('input');
  hex.type = 'text';
  hex.maxLength = 7;
  hex.spellcheck = false;
  hex.setAttribute('aria-label', '补边颜色编码');
  hex.style.cssText = 'box-sizing:border-box;flex:0 1 72px;width:72px;min-width:0;height:24px;padding:0 4px;margin:0;border:1px solid #777;border-radius:4px;background:var(--comfy-input-bg,#262626);color:inherit;font:12px monospace;';
  const eyedropper = document.createElement('button');
  eyedropper.type = 'button';
  eyedropper.textContent = '吸管';
  eyedropper.setAttribute('aria-label', '屏幕取色');
  eyedropper.style.cssText = 'box-sizing:border-box;flex:0 0 44px;width:44px;height:24px;padding:0;margin:0;border:1px solid #777;border-radius:4px;background:var(--comfy-input-bg,#343434);color:inherit;font:inherit;';
  row.append(label, swatch, hex, eyedropper);
  for (const type of ['pointerdown', 'mousedown', 'dblclick', 'keydown']) {
    row.addEventListener(type, event => event.stopPropagation());
  }

  let revision = 0;
  let pending = null;
  let pickError = false;
  const refresh = () => {
    const value = String(original.value ?? '#000000');
    if (document.activeElement !== hex) hex.value = value;
    const preview = HEX.test(value) ? value.toLowerCase() : '#000000';
    if (swatch.value !== preview) swatch.value = preview;
    const disabled = linked();
    swatch.disabled = hex.disabled = disabled;
    eyedropper.disabled = disabled || Boolean(pending) || !supported();
    eyedropper.title = disabled ? '颜色由连线控制' : !supported()
      ? '当前页面不支持屏幕取色；可点击左侧色块选色。'
      : pickError ? '取色未成功，请重试或使用调色盘。' : '点击后在屏幕上选择颜色，Esc 取消';
    eyedropper.style.cursor = eyedropper.disabled ? 'default' : 'pointer';
    eyedropper.style.opacity = eyedropper.disabled ? '0.5' : '1';
  };
  const setValue = value => {
    if (original.value !== value) revision++;
    original.value = value;
    hex.value = String(value ?? '');
    refresh();
  };
  const commit = value => {
    if (linked() || !HEX.test(value)) {
      hex.value = String(original.value ?? '');
      refresh();
      return;
    }
    const normalized = value.toLowerCase();
    if (normalized === original.value) {
      hex.value = normalized;
      return;
    }
    node.graph?.beforeChange?.();
    try {
      setValue(normalized);
      widget.callback?.call(widget, normalized, app.canvas, node);
    } finally {
      node.graph?.afterChange?.();
      node.setDirtyCanvas?.(true, true);
    }
  };

  node.widgets.splice(index, 1);
  const widget = node.addDOMWidget(FIELD, 'll_aspect_color', row, {
    ...original.options, serialize: true, margin: 0, hideOnZoom: true,
    getValue: () => original.value, setValue, onDraw: refresh,
    getMinHeight: () => ROW_HEIGHT, getMaxHeight: () => ROW_HEIGHT,
  });
  widget.callback = original.callback;
  widget.computeSize = width => [width ?? node.size?.[0] ?? 300, widget.hidden ? -4 : ROW_HEIGHT];
  widget.serializeValue = () => original.value;
  node.widgets.splice(node.widgets.indexOf(widget), 1);
  node.widgets.splice(index, 0, widget);

  swatch.addEventListener('change', () => commit(swatch.value));
  hex.addEventListener('change', () => commit(hex.value.trim()));
  hex.addEventListener('keydown', event => {
    if (event.key === 'Enter') hex.blur();
    if (event.key === 'Escape') {
      hex.value = String(original.value ?? '');
      hex.blur();
    }
  });
  eyedropper.addEventListener('click', async () => {
    if (!supported() || linked() || pending) return;
    const operation = new AbortController();
    const startRevision = revision;
    pending = operation;
    pickError = false;
    refresh();
    try {
      // Must be called synchronously from the user's click to retain activation.
      const result = await new globalThis.EyeDropper().open({signal: operation.signal});
      if (!operation.signal.aborted && revision === startRevision) commit(result.sRGBHex);
    } catch (error) {
      pickError = error?.name !== 'AbortError';
    } finally {
      pending = null;
      refresh();
    }
  });

  const onRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    pending?.abort();
    return onRemoved?.apply(this, args);
  };
  node.__llAspectColor = {refresh};
  refresh();
  if (node.size && node.computeSize && node.setSize) {
    const [width, height] = node.size;
    node.setSize([width, Math.max(height, node.computeSize()[1])]);
  }
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: 'LL.ImageAspectScale.PaddingColor',
  nodeCreated: enhanceAspectColor,
  loadedGraphNode(node) {
    enhanceAspectColor(node);
    node.__llAspectColor?.refresh();
  },
});
