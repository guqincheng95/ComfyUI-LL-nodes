# 后期UI布局修复 · v0.6.1

## 定位结果

可在插件代码中独立复现，无需先判定用户ComfyUI安装异常：

1. `addDOMWidget`默认margin为10，ComfyUI的DOM宿主宽高会减去`2 * margin`。旧代码上报标题30px、滑块62px或标题加滑块92px，但没有为这20px扣除留空间。
2. LiteGraph固定高度行通常额外增加4px间隔，因此旧版30px折叠标题实际宿主高度为`30 + 4 - 20 = 14px`。真实Chromium中标题向下超出16px。
3. 标题按钮原来是行内元素，可能再产生基线空隙。隐藏只用hidden标志，对仍按type判断可见性的旧宿主覆盖不足，收起时还可能留下间隙。
4. 原resize强制宽度至少360px，展开收起会覆盖用户手动缩窄的宽度。浏览器输入控件的固有宽度与主题盒模型也没有完整约束。

此前普通文档流浏览器适配器把控件直接排进容器，没有模拟ComfyUI宿主的边距扣除，因而未检测到该溢出。

## 修复

- 明确DOM margin为0，把左右10px留白放进插件自身border-box；上报高度就是内容高度。
- 标题设为块元素，限制输入框、按钮及滑块的宽高、padding、margin和盒模型；滑块允许随可用宽度收缩。
- 同步hidden和hidden类型，完全收起的控件抵消固定行4px间隙。
- 不主动修改画布缩放、浏览器缩放或接管ComfyUI坐标变换；由宿主统一缩放，插件内容在给定盒子内排版。
- 折叠重新计算高度，保留当前宽度，最低280px；维持既有24个序列化值、旧节点标识与折叠状态。

## 验证与复查

`tests/photo_layout.browser.mjs`使用真实Chromium，模拟官方DOM空间分配契约，覆盖18组宽度／画布缩放／折叠状态，并检查宿主边界、节点边界、内部滚动尺寸、鼠标点击定位、微调、保存恢复与主题尺寸覆盖。

开发环境运行（不是用户安装步骤）：

```bash
npm install --no-save --package-lock=false playwright@1.51.1
npx playwright install --with-deps chromium
node tests/photo_layout.browser.mjs
node tests/frontend.test.mjs
node tests/subject_frontend.test.mjs
```

这不是完整ComfyUI浏览器测试，也没有远程修改用户安装。本机更新整库后重启ComfyUI并Ctrl+F5；模型和Python依赖沿用已安装内容。如仍偏移，后续需要用户截图、ComfyUI前端版本及是否开启其他UI扩展，区分残余插件问题和宿主变换问题。

## 上游依据

- [官方DOMWidget默认margin与尺寸接口](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/src/scripts/domWidget.ts)
- [官方DOM宿主位置和尺寸计算](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/src/components/graph/DomWidgets.vue)
- [官方LiteGraph固定行高度与间隔](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/src/lib/litegraph/src/LGraphNode.ts)
- [较早的v1.24.0 DOMWidget可见性契约](https://github.com/Comfy-Org/ComfyUI_frontend/blob/v1.24.0/src/scripts/domWidget.ts)
