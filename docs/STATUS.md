# 当前状态 · 交接入口

- 日期：2026-10-13
- 仓库：guqincheng95/ComfyUI-LL-nodes
- 整库版本：0.3.0
- 已完成：原 ResolutionPreset v0.1.2 与 PhotoFinish v0.2.0 合并为一个 ComfyUI 插件入口；模块、前端、中文资源、示例、测试统一归类。
- 菜单：LL 节点库/图像工具/尺寸与比例；LL 节点库/图像后期/基础调色。
- 兼容：旧节点 ID、参数名、默认值、顺序保持；根 nodes.py/presets.py 为旧 Python 导入兼容层。
- 安装：custom_nodes/comfyui-LL-nodes；旧独立目录需用 scripts/migrate_legacy.py --apply 移出，备份在 custom_nodes 外。
- 更新：Git 安装一次 git pull；离线用户整库 ZIP 覆盖。
- 本地验证：比例 9 项、整库/迁移 4 项、前端 19 控件/399 位置检查通过；Python 编译检查通过。详见 TEST_REPORT.md。
- 待验证：用户真实 ComfyUI 安装、UI 渲染及图像执行；本轮未本地重跑 PyTorch 算法测试，已配置独立 CI 任务。

下次接手先读本文件，再按需读 CATEGORIES.md、相关模块与最新 CHANGELOG。历史日志位于 docs/history，不必每次通读。
