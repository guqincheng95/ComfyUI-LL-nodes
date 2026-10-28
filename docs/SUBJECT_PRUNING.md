# RMBG前景保真剪枝：外扩衣料、头饰与细节保护

版本v0.7.0，2026-10-28（北京时间）。节点仍为LLPersonSubjectClean，旧端口、输出序号和控件顺序保持兼容。

## 本轮问题与原因

用户样例：RMBG-2.0已将人物抠出，但外扩白色裙料／头花仍在；继续处理后手部略弱。接线图为external_mask、body_trim、关键点置信度0.60、分析1024、外扩1.25、肤色强度1.00，且RMBG整人MASK同时接到了skin_mask。

定位到的不同问题：

- 人物前景包含服装、头花，RMBG或SAM2的人物分割不等于“去饰品”。旧版没有独立头饰语义步骤。
- 旧几何修剪要求整套主关键点，遮挡关节被0.60阈值筛掉后可能整步跳过。外扩1.25是在放宽范围。
- 原遮罩被分析缩放、二值化和整体内部柔化，细指尖／软边会衰减；已合成黑底RGB再乘同一个Alpha，还会二次变暗。已核对[EasyUse原实现](https://github.com/yolain/ComfyUI-Easy-Use/blob/main/py/nodes/image.py)：add_background使用Alpha合成底色，和截图中的black设置一致。
- skin_mask用于可靠裸露皮肤取样，整个人物MASK会混入衣料，不应这样连接。

新版本采取“保留原抠像，仅对新删除区域应用门控”的流程，并提供独立可选的人体部位解析。不会靠调高肤色强度删除整件衣服，也不补画衣服遮挡的身体。

## 针对这组图片的接线

| 来源 | 节点输入 |
|---|---|
| RMBG-2.0的黑底image | image／原始图像 |
| 同一次RMBG-2.0的mask | foreground_mask／前景参考遮罩 |
| 同构图原深度，若使用 | depth_image／原始深度图 |
| 原始POSE_KEYPOINT，若使用 | keypoints／骨架关键点 |
| 可靠裸露皮肤MASK，可选 | skin_mask；没有就留空，不能接RMBG整人MASK |

若原始RGB还在，可继续输入原图，并将输入图像类型设为original。使用RMBG黑底结果时选择cutout_black；白底选择cutout_white。三个输入必须与同一次抠像、同裁切对应。部位模型本身不需要新POSE权重。

## 样例起点

| 参数 | 建议值 |
|---|---|
| 分割来源 | external_mask，沿用RMBG |
| 提取用途 | body_trim |
| 输入图像类型 | cutout_black（已抠黑底图） |
| 保留原抠像细节 | true |
| 部位语义剪枝 | atr_onnx（配置本地模型后），或external_masks |
| 清理头饰 | true |
| 贴身衣料保留量 | 0.10；默认0.15，越小越紧 |
| 外扩修剪倍率 | 1.0，先不用原来的1.25 |
| 关键点置信度 | 0.30，可按检测实际调整 |
| 分析最长边 | 1024 |
| 边界提炼强度／深度权重 | 0.70／0.60，有效深度才使用 |
| 肤色辅助边缘净化 | 先false；确有裸露肢体污染再开 |
| 手／脚保护 | true，范围沿用1.25／1.20 |
| 边缘柔化 | 1，仅柔化新裁切边界 |

部位语义默认off，避免更新后隐式加载新模型。**仅覆盖更新，不会自动启用头饰识别**。关闭时仍可使用既有轮廓／肤色流程，但不会凭空识别头花。新字段在旧字段之后追加；开关关闭时头饰／衣料细项收起但数值保留。

示例examples/subject/rmbg_pruning_workflow.json可直接拖入ComfyUI；通过两个LoadImage加载已抠图与白前景MASK文件，ImageToMask读取红通道。实际工作流可直接用RMBG的MASK输出替换文件支路，不能把LoadImage的透明度反相MASK当成普通灰度MASK。API格式为rmbg_pruning_api.json。

## 部位解析怎样使用

atr_onnx使用mattmdjaga/segformer_b2_clothes的18类ATR ONNX模型：身体、头发、脸、四肢和鞋作保留证据，服饰作候选剪枝区域。根据可见身体部位及躯干连接范围裁掉远离主体的衣料，保留贴近身体的服装；皮肤／手掌可直接保留RMBG原软边，不要求整套关节都可见。

头饰额外在自动定位的头部裁块内解析。高置信度脸／皮肤及头发有保护；头部局部的背景／帽饰证据只在原前景内删除。本样例白花虽被RMBG当作前景，部位解析可将其区分。该方法仍可能漏掉被分类为头发的饰品，不能保证所有头饰都自动去除；可接headwear_mask或exclude_mask纠正。

衣料保留量为可见身体宽度的比例，与外扩倍率共同作用；不是实际身体测量。缺少可靠可见下肢时会跳过衣料剪枝并报告，不从一小块头部推断整身。完全遮挡身体的服装无法由此恢复其内部轮廓。CPU执行部位模型，复用现有Torch/CUDA环境，不安装GPU ONNX包。

external_masks无需本地ONNX模型，接已有且获授权的人体解析输出：

- body_part_mask：身体核心、脸发、肢体和需要保留的贴身躯干范围，不能使用整个人物MASK代替。
- garment_mask：允许裁剪的衣料区域，必须与body_part_mask一起提供；不表示直接删除全部衣服。
- headwear_mask：明确的头饰区域，单独提供也可只处理头饰。

用户protect_mask优先于自动语义删除；用户exclude_mask最终优先于所有自动／显式保护。自动语义删除优先于宽泛的脚掌／手掌几何保护，避免宽范围将裙尾再次恢复。

## 本地ATR模型配置与许可

运行代码与权重分开。上游模型明确采用[NVIDIA SegFormer许可](https://github.com/NVlabs/SegFormer/blob/master/LICENSE)，其用途限于非商业研究／评估；本插件的MIT许可不替代权重许可。权重不随代码ZIP分发。商业流程应使用已获授权的外部部位MASK，或另行取得相关权重许可。

仅做研究／评估时，可使用已核对的官方模型文件：

- 路径：ComfyUI/models/segformer_b2_clothes/onnx/model.onnx
- 大小：110039290字节，约110MB。
- SHA256：a93a8dac171b5c1fcc53632a8bfc180bfd9759ea69a3e207451bb07f76add54f
- 固定修订：584abc1e1d260e23c0fc627c5217a09b2b461046
- 下载：[官方ONNX文件](https://huggingface.co/mattmdjaga/segformer_b2_clothes/resolve/584abc1e1d260e23c0fc627c5217a09b2b461046/onnx/model.onnx)

**Windows PowerShell**，用户已验证的整合包Python路径：

    & 'L:\AI\ComfyUI-aki-v3.2\python\python.exe' 'L:\AI\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-LL-nodes\scripts\setup_subject_pruning.py' --install-runtime --download

这条命令执行脚本文件，不使用多行python -c。复用已安装onnxruntime；缺少时仅补该CPU运行时，并锁定当前NumPy版本。不会安装／升级Torch、torchvision、CUDA或重新下载SAM2。模型下载校验大小和SHA256，失败不覆盖旧文件；只有显式--download才联网。

无外网时在其他设备下载文件后复制至上述路径；安装onnxruntime可使用本机已有包或匹配Python版本的离线wheel。脚本支持--model-url指定HTTPS镜像完整地址，原SHA256校验保持不变。LL_PARTS_MODEL环境变量可指定模型文件。

完成后重启ComfyUI、Ctrl+F5，按上表启用部位语义剪枝。未配置模型却选atr_onnx会明确报错，不会静默跳过；运行时也校验大小／SHA256，防止把其他18类模型误当成ATR标签布局。

## 抠像保真与诊断

preserve_foreground在external_mask模式保留原生分辨率软遮罩，只缩放新增删除门控；未删区域不再经历遮罩缩放和全局边缘柔化。没有有效深度时不会对已抠前景再进行一次RGB抠像；有深度则保留其局部删除证据，身体部位保护和明确MASK仍生效。

input_image_mode处理已合成黑／白底RGB的重复Alpha问题。它依赖同一次抠像MASK，不能恢复被原抠图删掉的颜色。错误选择黑／白底模式也会错误处理边缘；原始RGB使用original。

skin_mask覆盖超过原人物65%时会提示“疑似误接整人RMBG MASK”，忽略该取样提示并改为保守自动取样；这只是接线检查，不是精确肤色语义判别。肤色步骤缺少有效深度或可靠样本仍会跳过。

report.semantic_pruning说明衣料／头饰处理、部位像素和自动头部框；像素数单位为分析画布，不是识别精度。保留率以排除明确语义删除后的基线计算，不能把retained_fraction=1理解成全部原衣料都保留。stage_preview第二栏包含RGB／深度与语义提炼。

## 本次验证边界

使用用户截图右侧原始RMBG预览裁块（376×698）实际运行完整节点和官方ONNX模型；前景MASK由预览非黑像素估计，用户原始RMBG软MASK／未缩小RGB／POSE／深度均未随图提供。用户涂画灰色区域没有用于算法输入。主要裙尾和白花已被删除，抽查手部787个前景像素RGB最大差为0。

这不是本机全分辨率或最终SD生图验收，也没有重跑RMBG本身。真实软边保真由独立的亚像素遮罩、细指尖降采样、黑／白底重复Alpha等回归覆盖。模型识别仍可能出错，贴身衣料保留范围仍为有界估计。实测记录见pruning-real-check.json。
