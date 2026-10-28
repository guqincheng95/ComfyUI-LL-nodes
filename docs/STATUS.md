# 当前状态 · 交接入口

- 日期：2026-10-28（北京时间）；版本v0.7.0。仓库guqincheng95/ComfyUI-LL-nodes。
- 本轮：RMBG保真门控保留原生软边，新增已合成黑／白底输入，避免重复Alpha；只柔化新裁切边界。
- 可选atr_onnx／external_masks部位语义，剪外扩衣料／头饰并保留身体部位，缺整套骨架也可执行；语义默认off，仅更新不会自动去头饰。
- 本地约110MB ONNX＋CPU onnxruntime；执行时不联网、不改Torch/CUDA。权重限NVIDIA研究／评估，不随ZIP分发；商业流程接已获授权外部部位MASK。
- 本例接线／参数／一次配置见SUBJECT_PRUNING.md。skin_mask不能接整人RMBG MASK，建议先关肤色；输入cutout_black，trim_scale1.0，garment_margin0.10。
- 101项Python（原85＋新16）与前端检查通过；实际节点跑376×698截图右侧RMBG预览，未用灰色涂画，主要白花／裙尾去除，787手部抽查像素RGB差0。非全分辨率／实际软MASK／POSE／深度／GPU／SD验收，见pruning-real-check.json。

以下为v0.6.x沿用记录：

- 本轮：修复完整脚掌／鞋与掌心覆盖不足，新旧两个节点均追加独立脚掌保护／范围1.20、手掌保护／范围1.15；两项保护默认开，肤色仍默认关。原腿／臂倍率不负责手脚调节。
- 增强节点自动保护仅保留初始分割已有区域；SAM2补有效手脚细点提示。缺细点局部估计、缺端点跳过，报告列部位／来源；明确删除最后优先。DWPose可选部位null与BODY25脚点已适配。
- 使用指南SUBJECT_CLEAN.md已按完整讲解重写，含输入／模式／深度／外扩／肤色与材质边界／输出／场景／脚掌手掌排错，旧文档与示例同步。新增四个参数optional追加，旧工作流默认使用新保护，可关掉对照。
- 本轮85项Python（含12项手脚回归）及前端控制检查通过；合成完整脚掌／鞋／手与公开COCO鞋靴标注样例检查完成，见extremity-check.json。不等于用户真实分割、POSE或最终生成精度；用户失败样例仍待回归。
- 本轮后期UI修复：定位到默认DOM上下边距使实际空间不足；统一高度与内部留白、折叠标题块布局、窄宽度／主题尺寸与新旧隐藏契约。算法和模型依赖不变。
- 真实Chromium按ComfyUI DOM布局契约复现旧版16px溢出；修复后18组宽度／画布缩放／折叠状态、鼠标定位、保存恢复和主题尺寸检查通过。完整ComfyUI用户端仍待确认。
- 新增LLPersonSubjectClean；旧ResolutionPreset、AIVisualPhotoFinish、LLPersonContourTrim保留。旧工作流不自动换节点。
- 已完成：原RGB人物语义引导SAM2.1、局部RGB/深度分水岭提炼、人物/外扩修剪、RGB/RGBA/原深度同MASK输出、强制保留/删除、阶段预览与报告。
- 肤色增强默认关闭，开关展开3个参数。基于肢体内部色度统计+局部深度异常，只检查边缘；自动皮肤取样是启发式，支持显式skin_mask，缺少深度或可靠样本跳过。
- 推荐semantic_sam2：需DeepLab MobileNetV3与SAM2.1本地权重。依赖/离线安装见SUBJECT_SETUP.md；节点不下载、不安装、不更换Torch/CUDA。external_mask模式不加载模型。
- v0.6历史真实Tiny+人物语义+新推理DepthAnythingV2 Small检查完成；电竞椅样例主要椅背/扶手残留减少，肩后仍有少量残留。该记录不冒充本轮新模型推理。
- 真实样例使用手工可见骨架和重新生成深度；不是用户实际POSE/深度。无骨架半身图已验证自动提取，可能保留多人。GPU/完整ComfyUI/最终SD生图仍待实测。
- 三阶段预览从左到右：初始主体、RGB/深度提炼、最终修剪；skin_removed_mask只标肤色步骤新增删除区域。
- 后续优先：拿用户原始RGB+深度+POSE回归；宽裙/头饰/交叉肢体等端到端难例仍需补充。近肤色衣物、同深度家具、缺关键点和强遮挡仍可能误差，不能宣称所有图片自动抠净。
- 更新整库后需新建“LL人物主体提取”使用增强功能。未接深度时clean_depth是全黑占位，不应接深度条件。

固定读取顺序：本文件 → 对应模块文档（当前RMBG／去饰品读SUBJECT_PRUNING.md，总功能读SUBJECT_CLEAN.md，后期UI读PHOTO_UI_LAYOUT.md）→ 本轮DEVELOPMENT_LOG；按需读SUBJECT_SETUP.md、TEST_REPORT.md。无需通读history。v0.5状态和验证归档在history/library-v0.5.0/。
