# 当前状态 · 交接入口

- 日期：2026-10-24（北京时间）；版本v0.6.1。仓库guqincheng95/ComfyUI-LL-nodes。
- 本轮后期UI修复：定位到默认DOM上下边距使实际空间不足；统一高度与内部留白、折叠标题块布局、窄宽度／主题尺寸与新旧隐藏契约。算法和模型依赖不变。
- 真实Chromium按ComfyUI DOM布局契约复现旧版16px溢出；修复后18组宽度／画布缩放／折叠状态、鼠标定位、保存恢复和主题尺寸检查通过。完整ComfyUI用户端仍待确认。
- 新增LLPersonSubjectClean；旧ResolutionPreset、AIVisualPhotoFinish、LLPersonContourTrim保留。旧工作流不自动换节点。
- 已完成：原RGB人物语义引导SAM2.1、局部RGB/深度分水岭提炼、人物/外扩修剪、RGB/RGBA/原深度同MASK输出、强制保留/删除、阶段预览与报告。
- 肤色增强默认关闭，开关展开3个参数。基于肢体内部色度统计+局部深度异常，只检查边缘；自动皮肤取样是启发式，支持显式skin_mask，缺少深度或可靠样本跳过。
- 推荐semantic_sam2：需DeepLab MobileNetV3与SAM2.1本地权重。依赖/离线安装见SUBJECT_SETUP.md；节点不下载、不安装、不更换Torch/CUDA。external_mask模式不加载模型。
- 73项Python测试和2套前端控制检查通过。真实Tiny+人物语义+新推理DepthAnythingV2 Small检查完成；电竞椅样例主要椅背/扶手残留减少，肩后仍有少量残留。
- 真实样例使用手工可见骨架和重新生成深度；不是用户实际POSE/深度。无骨架半身图已验证自动提取，可能保留多人。GPU/完整ComfyUI/最终SD生图仍待实测。
- 三阶段预览从左到右：初始主体、RGB/深度提炼、最终修剪；skin_removed_mask只标肤色步骤新增删除区域。
- 后续优先：拿用户原始RGB+深度+POSE回归；宽裙/头饰/交叉肢体等端到端难例仍需补充。近肤色衣物、同深度家具、缺关键点和强遮挡仍可能误差，不能宣称所有图片自动抠净。
- 更新整库后需新建“LL人物主体提取”使用增强功能。未接深度时clean_depth是全黑占位，不应接深度条件。

固定读取顺序：本文件 → 对应模块文档（后期UI读PHOTO_UI_LAYOUT.md，人物提取读SUBJECT_CLEAN.md）→ 本轮DEVELOPMENT_LOG；按需读SUBJECT_SETUP.md、TEST_REPORT.md。无需通读history。v0.5状态和验证归档在history/library-v0.5.0/。
