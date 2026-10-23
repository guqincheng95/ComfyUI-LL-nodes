# 人物轮廓修剪示例

把 minimal_workflow.json 拖进 ComfyUI。选择原图与现有 SDPose 权重。示例使用官方 SDPoseKeypointExtractor 和 comfyui_controlnet_aux 的 DepthAnythingV2Preprocessor，均应已安装并有权重。

默认未接 foreground_mask，运行时会使用骨架保留范围。建议从你已有的 BEN2 背景移除节点把 MASK 接入原图人物遮罩端口，提升宽度贴合与背景空隙保留。

查看三张预览：修剪深度、白色保留遮罩、绿保留/红删除对比。满意后将“修剪后深度图”接回原来混合图像的深度支路。详细说明见 ../../docs/CONTOUR_TRIM.md。

示例已做 JSON、节点输入及连接一致性检查，尚未在实际 ComfyUI 浏览器运行。
