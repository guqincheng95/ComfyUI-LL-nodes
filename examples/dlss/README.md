# DLSS5 增强示例

**只增强整图**：使用 native_api.json，仅需 original.png，不接设置或遮罩。

**分区增强**：使用 minimal_api.json，按下文准备人物遮罩。

先配置运行时，见 [DLSS5.md](../../docs/DLSS5.md)。将原图以 original.png、白人物黑背景的灰度遮罩以 person_mask.png 上传至 ComfyUI input。API 示例采用 LoadImageMask 的 red 通道直接读取白色选区，不使用 LoadImage 的反向透明 MASK。

人物 MASK 可替换为已有语义／背景移除节点的输出。可选皮肤 MASK 连接增强节点 skin_mask；本例不假设本地安装了哪种分割模型。节点输出 image 可保存，report 可连接显示文本。

预览先打开 preview_mode，正式导出请关闭后重新运行。API 示例调用前请确保已上传上述两个文件。
