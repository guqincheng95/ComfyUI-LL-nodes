# 当前状态 · 交接入口

- 日期：2026-10-23 UTC；仓库 guqincheng95/ComfyUI-LL-nodes；整库版本 0.5.0。
- 整库三个节点：ResolutionPreset、AIVisualPhotoFinish、LLPersonContourTrim；单目录安装与更新，中文分级分类。
- 本轮后期优化：可选 reference_image，off／original／reference 三种模式；总强度、明暗匹配、颜色匹配独立设置。匹配先于既有手动调色。
- 原图对齐面向同构图不同分辨率的颜色漂移；参考仿色匹配不同图片的明暗分位数及三明度区域颜色统计，非语义风格迁移。
- 曝光、色温、色调三个默认收起的面板；参数在隐藏时生效、保存恢复展开状态及数值。19 个手动滑块增加黑白／互补色色带，保留精确输入与按钮。
- 旧 19 个 FLOAT 与布尔控件顺序及节点类型不变，新自动参数为 optional 并追加，旧 API 与工作流默认关闭匹配。
- PyTorch 2.9.1+cpu、Python 3.12：54 项测试通过（新匹配13、轮廓13、后期15、比例9、整库4）；前端19控件／399位置及折叠／色带检查通过。
- Chromium 134 真实 DOM 适配器检查通过：展开收起、微调、布尔开关、自动选择器、24个控件值及展开状态保存恢复，控制台无错误。适配器不是完整 ComfyUI 前端。
- 真实照片加已知模拟色偏与2倍放大的检查已完成；恢复目标颜色接近原图。记录见 photo-match-metrics.json，不能据此保证实际重采样的校正百分比。
- 用户 ComfyUI 服务端、GPU、实际二次采样图片与完整生图链路仍待实测；没有声称已远程部署。
- 人物轮廓 v0.4.0 功能保留：接原深度、SDPose／DWPose关键点与可选前景／保护／去除 MASK，修剪外扩服饰，不补画身体。见 CONTOUR_TRIM.md。
- 比例预设：6种比例包含2:3，原对齐尺寸与 Krea2 适配保留。
- 更新一次整库 ZIP 或 git pull；重启后 Ctrl+F5。已经完成旧目录迁移的安装无需再次迁移。

后续优先读本文件与 PHOTO_COLOR_MATCH.md，按需查 PHOTO_MATCH_RESEARCH.md、CONTOUR_TRIM.md 和 CHANGELOG.md。历史验证记录在 history/。
