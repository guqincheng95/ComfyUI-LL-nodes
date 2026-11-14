# DLSS5 单节点示例

- native_api.json：上传original.png，只使用一个LL图像增强节点进行原版整图增强。
- minimal_api.json：再上传person_mask.png，白人物黑环境；同一个主节点选择人像保真、接人物MASK并开启节点内局部对比。

不需要额外设置节点或对比节点。人物MASK可替换为已有语义分割输出；可选皮肤MASK接skin_mask。加载灰度MASK使用LoadImageMask的red通道，不使用LoadImage的反向Alpha MASK。首次环境部署及参数详见[DLSS5.md](../../docs/DLSS5.md)。
