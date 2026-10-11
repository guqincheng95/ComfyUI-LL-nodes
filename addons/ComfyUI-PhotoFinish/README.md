# Photo Finish · 基础后期 v0.2.0

用于 ComfyUI 的独立后期调色节点：19 个数字参数 + 保持明度开关。
输入 IMAGE，输出 IMAGE；处理 PNG/JPG 加载后的浮点图像。19 项滑块与数值/箭头精细控制，无模型下载。

## 安装（无需服务器连接外网）

把交付 ZIP 上传到 `ComfyUI/custom_nodes` 后解压。最终目录必须是：

```text
ComfyUI/custom_nodes/ComfyUI-PhotoFinish/__init__.py
```

用户当前服务器首次安装命令：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes
python -m zipfile -e ComfyUI-PhotoFinish-v0.2.0.zip .
```

重启 ComfyUI，刷新浏览器，搜索 **后期修图**、**曝光**、**白平衡**、**色彩平衡** 或 **Photo Finish**，分类为 **AI 视觉 / 后期修图**。
不需要 pip install，不更换现有 Torch、CUDA、Triton 或其他环境依赖；仅使用 ComfyUI 已有 PyTorch。
已有同名目录时先将其备份到 custom_nodes 外，再解压更新，避免重复注册。

源码暂存于现有 ComfyUI-ResolutionPreset 仓库的 `addons/ComfyUI-PhotoFinish` 子目录。
**它是独立插件**：只安装整个 ResolutionPreset 仓库不会自动加载本节点；需把该子目录复制到 custom_nodes 下。尺寸节点的注册与算法没有改动。

## 怎么连接

`加载图像 / VAE 解码 → Photo Finish → 预览图像 / 保存图像`

导入 `examples/minimal_workflow.json` 后，在 LoadImage 中选择你的图片即可。
建议独立的“加载图像→调色→保存”工作流，反复调色不需要重新生图。
改参数后点击运行生效，不是拖动实时预览。所有参数归零即可恢复原图。

## 参数说明

所有参数默认 0，保持明度默认开启。曝光 -5..+5 EV，步长 0.05；其他参数 -100..+100，步长 1。

| 参数名 | 中文 | 正数的作用 |
|---|---|---|
| exposure | 曝光 | 提升线性曝光；+1 EV 为线性光量翻倍 |
| contrast | 对比度 | 压暗暗部、提亮亮部，中性支点约为感知亮度 0.5 |
| highlights | 高光 | 提亮亮部层次；负数压低高光 |
| shadows | 阴影 | 提亮暗部层次；负数加深阴影 |
| whites | 白色 | 提升白端，允许产生白色截断；负数收回白端 |
| blacks | 黑色 | 抬高黑位；负数压低黑端，允许产生黑色截断 |
| temperature | 色温偏移 | 偏暖；负数偏冷，不是绝对 Kelvin |
| tint | 色调偏移 | 偏洋红；负数偏绿 |
| vibrance | 自然饱和度 | 优先增强低饱和颜色，无专门的人脸/肤色识别 |
| saturation | 饱和度 | 整体增强色彩；-100 变灰度 |
| shadow_cyan_red | 阴影 青—红 | 偏红；负数偏青 |
| shadow_magenta_green | 阴影 洋红—绿 | 偏绿；负数偏洋红 |
| shadow_yellow_blue | 阴影 黄—蓝 | 偏蓝；负数偏黄 |
| midtone_cyan_red | 中间调 青—红 | 偏红；负数偏青 |
| midtone_magenta_green | 中间调 洋红—绿 | 偏绿；负数偏洋红 |
| midtone_yellow_blue | 中间调 黄—蓝 | 偏蓝；负数偏黄 |
| highlight_cyan_red | 高光 青—红 | 偏红；负数偏青 |
| highlight_magenta_green | 高光 洋红—绿 | 偏绿；负数偏洋红 |
| highlight_yellow_blue | 高光 黄—蓝 | 偏蓝；负数偏黄 |
| preserve_luminosity | 保持明度 | 保持分区色彩平衡前的线性亮度，不撤销曝光调整 |

注意 tint 的正方向为洋红；色彩平衡 magenta_green 的正方向为绿色，与两种控件的常见语义一致。

## 调节建议

先白平衡，再光影六项，再分区色彩平衡，最后饱和度。初次建议曝光 ±0.2～0.5 EV、其他参数 ±5～20 起步。
参数刻度与 LayerStyle、Camera Raw 不通用，不能照搬旧值。旧版独立“亮度”由曝光和分区光影控制承担，没有单独同名滑块。

## 图像与性能

- 按显示参照 sRGB 解释输入，在 float32 中处理；无中间 PIL / uint8 转换。
- PNG 无损并不自动等于高动态范围或 16 位；本节点不能恢复加载器已经丢掉的精度或已截断的细节。
- 保留宽高、批次数和设备；支持 RGB/RGBA，Alpha 不参与调色。
- 输入通常来自 ComfyUI CPU IMAGE，因此一般在 CPU 执行；若输入在 GPU，则沿用该设备。本版实测为 CPU。
- 按行分块限制中间张量内存；输出整幅图像仍需内存。支持批量逐图处理。
- 非零调整输出 float32；全部归零时原样返回输入。
- 色彩超出 sRGB 范围时压缩色度，避免简单逐通道截断造成明显色偏。极端调整仍可能失去层次或降低饱和度。
- 本版不读取 ICC、不处理 RAW/线性 HDR、不做局部蒙版或细节重建，不复刻 Adobe 专有算法。

## 验证

已执行的结果见 `docs/TEST_REPORT.md`；目标服务器验收：

```bash
# 在 ComfyUI 原有 Python 环境、插件目录内：
python -m unittest discover -s tests -v
```

导入示例工作流，零参数运行一次，再单独改曝光到 +0.5、色温到 +20、阴影到 +30，确认图像变化且尺寸不变。
当前没有访问你的服务器；真实服务器导入、界面及 CUDA 验收待执行。

## 中文界面（2026-10-10）

重启 ComfyUI 并按 Ctrl+F5 强制刷新浏览器。在 ComfyUI 设置的语言选项中选择“中文 / Chinese”，节点参数、下拉选项和接口标签会使用中文。原始英文参数键、节点类型、选项值与控件顺序保持不变，已有工作流与 API 调用兼容。节点中英文名称均保留，便于搜索。

采用官方 locales/zh/nodeDefs.json 翻译机制，翻译无需额外依赖；v0.2.0 的滑块由随包 web 前端扩展提供。若手动给旧节点改过标题，该标题不会被强制覆盖，可重新命名或新建节点。

## v0.2.0 · 第二版滑块

每项参数包含中文名称、精确数值框、◀ / ▶ 微调按钮及下方滑块。

- 左负右正，中心为 0；负向 10 档、正向 10 档，加零位共 21 个位置（20 段）。
- 曝光范围 −5～+5 EV，滑块每档 0.5 EV，按钮每次 0.05 EV。
- 其他 18 项范围 −100～+100，滑块每档 10，按钮每次 1。
- 数值框支持直接输入；滑块双击归零，也可用键盘左右键逐档移动。
- 旧工作流的 0.30、−6 等精细值保持不变，仅主动操作滑块时吸附到整档。
- 原有参数名、数量、顺序和算法不变。端口连接外部数值时禁用对应本地控件。
- 操作只改变参数，仍需运行工作流查看调色结果，不是实时图像预览。

覆盖解压后必须重启 ComfyUI 并 Ctrl+F5，确认 `web/controls.js`、`web/photo_finish.js` 已一起安装。节点会增高以容纳滑块。前端扩展未加载时仍保留原数值控件，可检查浏览器控制台与 ComfyUI 启动日志。
