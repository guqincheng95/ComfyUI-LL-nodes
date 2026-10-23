# 成熟技术调研与采用记录

查阅日期：2026-10-23；整库交付：2026-10-24。

| 现有技术/项目 | 核对内容 | 本版采用方式 |
|---|---|---|
| ComfyUI 官方 SDPose | comfy_extras/nodes_sdpose.py：POSE_KEYPOINT 为 canvas_width/canvas_height/people，身体18点，脸70点，双手各21点，脚6点；像素坐标 | 直接接现有模型输出，不重复训练或检测；手脚范围使用已有 wholebody 关键点 |
| FASHN VTON 1.5 | preprocessing/masks.py：成熟的遮罩边界处理、形态学扩张和轮廓平滑方法；Apache-2.0 | 借鉴遮罩细化思路；直接使用 Pillow 成熟绘图/MaxFilter/GaussianBlur 实现，无粘贴上游代码 |
| Cozy Human Parser | 已有 ComfyUI 人体/服装部位 MASK，包含帽子、头发、四肢等类别 | 提供 protect_mask/exclude_mask 直接衔接其现有输出，不封装或下载额外分割模型 |
| FASHN Human Parser | 18类语义解析、衣服/帽子/手脚等分类；模型有独立许可证 | 确认语义分割擅长类别，不能单凭删除裙子类别恢复原体型；可作为外部分割来源，不内置权重或代码 |
| Pillow / NumPy | 已在 ComfyUI 环境中的成熟图像与数值工具 | 实际调用图形栅格化、形态学与滤波函数，图像数据保持浮点 |

新增代码负责接线、坐标/批量适配、局部边界观测、保留范围约束和安全回退；不是一个新的分割网络或人体重建模型。直接依赖 ComfyUI 已有 PyTorch、NumPy、Pillow，无网络请求。

来源：
- https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_sdpose.py
- https://github.com/Fannovel16/comfyui_controlnet_aux/blob/main/node_wrappers/depth_anything_v2.py
- https://github.com/fashn-AI/fashn-vton-1.5/blob/main/src/fashn_vton/preprocessing/masks.py
- https://github.com/fashn-AI/fashn-vton-1.5/blob/main/LICENSE
- https://github.com/cozymantis/human-parser-comfyui-node
- https://github.com/fashn-AI/fashn-human-parser

真实人物目视检查使用 OpenMMLab MMPose tests/data/coco 的公开 COCO WholeBody 标注样例 785。输入为标注关键点和分割多边形，不是运行 SDPose 或 BEN2 推理。检查在 RGB 上展示保留范围，不是生成图像效果验证。照片未收入发行包。
