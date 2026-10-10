# 开发日志与交接

## 2026-10-10 · 0.1.0

- 确认范围：光影六项、色温/色调/自然饱和度/普通饱和度、三明度区各三通道、保持明度。
- 查阅 LayerStyle、GPUImage2、darktable 的实际源码和许可证，选型记录见 ALGORITHMS.md。
- 完成 PyTorch float32 图像管线、sRGB 转换、明度曲线、连续分区、色度压缩和原生节点接口。
- 所有参数零值中性；支持 RGB/RGBA、批量和分块；没有 PIL 8 位中间转换。
- 修正测试对浮点 SIMD 分块输出逐位一致的不合理假设，采用经测量支持的绝对容差，输入和 Alpha 仍严格保持。
- 15 项测试通过，完成六组真实照片目视检查与 4K CPU 性能测试。
- 提供独立 ZIP、中文说明、UI/API 示例 JSON。
- 源码保存在现有仓库 addons/ComfyUI-PhotoFinish 中，独立安装、独立注册；不改变尺寸预设节点。

## 下一步目标机验收

1. 解压至 custom_nodes/ComfyUI-PhotoFinish，重启 ComfyUI。
2. 搜索 Photo Finish，确认 19 数值和保持明度开关。
3. 导入 examples/minimal_workflow.json，选择测试 PNG，零值及几个非零组合分别运行。
4. 测试实际常用生图结果，尤其强高光、弱光肤色和鲜艳色彩；依据反馈调整参数响应。
5. 得到真实服务器日志及输出后，再标记目标环境验收通过。

本版无实时预览/曲线编辑器/RAW 解码/ICC 转换/自动更新，未越过确认范围。
