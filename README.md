# comfyui-LL-nodes · LL 个人节点库

**v0.11.1** · 一个目录安装 · 一次更新全部节点 · 中文分类与搜索

DLSS5 最短路径：**加载图片 → LL DLSS5 图像增强 → 保存图片**。不接设置、不接遮罩时，使用原作者默认参数并输出原生增强RGB。需要分区时再接设置或遮罩。

新增 [DLSS5 分区光影增强](docs/DLSS5.md)：一次整图神经渲染，人物／环境分区强度、统一光影、边缘与肤色保护、局部对比及视频帧光流稳定。首次使用双击 `setup_dlss5.bat` 自动检查并补齐兼容运行时；ComfyUI-Manager 标准安装可通过 `install.py` 自动调用。需 Windows＋兼容 NVIDIA RTX，驱动／画质仍需本机自检。普通git更新不执行安装脚本。

| ComfyUI 分类 | 节点 | 功能 |
|---|---|---|
| LL 节点库 / 图像工具 / 尺寸与比例 | LL 比例预设 | 6 种比例、3 档尺寸、方向与自定义宽高；含 2:3 |
| LL 节点库 / 图像工具 / 尺寸与比例 | LL 图像比例控制 | 可独立计算宽高；图像与遮罩同步裁切、补边、拉伸 |
| LL 节点库 / 图像工具 / 人物轮廓 | LL 人物轮廓修剪 | 结合原图前景与骨架裁掉头饰、裙摆等外扩深度；支持批量和对比预览 |
| LL 节点库 / 图像工具 / 人物轮廓 | LL 人物主体提取 | 原始RGB／RMBG保真，深度细化，可选部位语义去裙尾／头饰，同MASK输出RGB／深度 |
| LL 节点库 / 图像后期 / 基础调色 | LL 人像色彩对齐 | 中性色校白平衡、分区肤色匹配、手动调色实时预览 |
| LL 节点库 / 图像后期 / 兼容与整图仿色 | LL 后期修图（兼容版） | 原图对齐、整图仿色、手动调色实时预览 |
| LL 节点库 / 图像后期 / DLSS5 神经增强 | LL DLSS5 增强设置 | 人像／均衡／环境预设、原生光影与结构、区域和边缘参数 |
| LL 节点库 / 图像后期 / DLSS5 神经增强 | LL DLSS5 图像增强 | 只接图像原生直出；可选人物／皮肤MASK与分区增强 |
| LL 节点库 / 图像后期 / DLSS5 神经增强 | LL DLSS5 局部对比 | 完整增强后裁ROI，左原图右结果；支持检查遮罩 |

换装或换背景时，参见 [人像色彩对齐](docs/PORTRAIT_COLOR_ALIGN.md)。预览开关和重复安装清理见 [实时预览](docs/PHOTO_LIVE_PREVIEW.md)。

图像比例控制可不接图像或遮罩，直接按比例、目标尺寸和像素倍数输出宽高。旧比例预设照常使用。用法及示例见 [IMAGE_ASPECT_SCALE.md](docs/IMAGE_ASPECT_SCALE.md)。

v0.7 新增RMBG原抠像保真、已合成黑／白底输入、可选部位语义剪枝与头饰清理；设置与一次配置见[SUBJECT_PRUNING.md](docs/SUBJECT_PRUNING.md)。本地ATR需额外约110MB ONNX和CPU运行时，权重限研究／评估；已获授权的人体部位MASK可从external_masks接入，不需要该模型。语义默认关闭，不自动下载或修改Torch/CUDA。

独立手脚保护及完整功能见[SUBJECT_CLEAN.md](docs/SUBJECT_CLEAN.md)。

保留v0.6.1后期折叠／滑块布局修复，记录见[PHOTO_UI_LAYOUT.md](docs/PHOTO_UI_LAYOUT.md)。

v0.6新增增强人物主体提取节点。接线见 [SUBJECT_CLEAN.md](docs/SUBJECT_CLEAN.md)，首次依赖与两份模型安装见 [SUBJECT_SETUP.md](docs/SUBJECT_SETUP.md)，立项与验收记录见 [SUBJECT_V06_PLAN.md](docs/SUBJECT_V06_PLAN.md)。旧节点保留兼容，需新建增强节点使用新功能。

后期修图保留自动原图对齐、参考仿色与三个折叠区，所有手动滑块具有方向色带。接线和使用见 [PHOTO_COLOR_MATCH.md](docs/PHOTO_COLOR_MATCH.md)，双图示例在 `examples/photo/reference_match_*`。

人物轮廓修剪的接线与参数说明见 [CONTOUR_TRIM.md](docs/CONTOUR_TRIM.md)，示例在 `examples/contour/`。

搜索 `LL` 查看本库节点，也可搜索“比例预设”“后期修图”“曝光”“白平衡”“自动仿色”或原英文名称。
旧工作流使用的 `ResolutionPreset`、`AIVisualPhotoFinish` 类型标识保持不变，连接和参数顺序保持兼容。

## 首次安装

在 ComfyUI 根目录执行：

```bash
git clone https://github.com/guqincheng95/ComfyUI-LL-nodes.git custom_nodes/comfyui-LL-nodes
```

也可把交付 ZIP 上传至 `custom_nodes` 后解压，最终入口为 `custom_nodes/comfyui-LL-nodes/__init__.py`。不要把 `modules` 中的文件夹单独安装。

原节点沿用现有依赖。增强人物节点需要额外依赖和本地模型，按 SUBJECT_SETUP.md 配置；代码ZIP不包含模型。DLSS5 依赖使用上方独立脚本自动部署，支持离线 ZIP、已有运行时和自选镜像；安装脚本不更换 Torch/CUDA/驱动。节点导入和执行时不会自动下载或安装。

## 从两个独立插件迁移（只需一次）

停止 ComfyUI 后，把 `comfyui-LL-nodes-v0.11.1.zip` 上传至 `custom_nodes`：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes
python -m zipfile -e comfyui-LL-nodes-v0.11.1.zip .
python comfyui-LL-nodes/scripts/migrate_legacy.py --apply
```

迁移脚本将已识别的旧 `ComfyUI-ResolutionPreset`、`ComfyUI-PhotoFinish`（含 `-main`）及重复的统一节点库目录移到 ComfyUI 根目录的 `ll-nodes-backups/时间戳/`，不删除旧文件。避免新旧插件同时注册同名节点。其他改过名字的旧目录需要自行移到 `custom_nodes` 外。

若过去手工修改过 `presets.py`，自定义内容仍在备份中，可按需合并到新版 `modules/resolution/presets.py`；脚本不会擅自覆盖新版预设。

重启 ComfyUI，界面语言选择中文，浏览器 Ctrl+F5。旧节点若曾手工改标题会保留原标题；新建节点可看到 LL 名称。

## 后续统一更新

Git 安装：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes/comfyui-LL-nodes
git pull --ff-only
```

ZIP 安装：下载新的整库 ZIP 并在 `custom_nodes` 覆盖解压。ZIP 安装不包含 Git 历史，不能直接 git pull。两种方式都会同时更新比例预设、人物轮廓、后期修图、前端和翻译，最后重启并刷新。

若原比例插件目录本身是 Git 克隆，也可以直接在原目录更新；新的入口会加载整个节点库。随后运行该目录的 `scripts/migrate_legacy.py --apply` 移走独立后期插件。目录重命名不是工作流兼容的前提。

## 目录与文档

| 路径 | 用途 |
|---|---|
| `__init__.py` | 整库唯一节点注册入口与版本 |
| `modules/resolution/` | 尺寸与比例节点、预设表 |
| `modules/subject/` | 增强人物语义、SAM2、深度与肤色净化 |
| `modules/contour/` | 人物轮廓、关键点适配和遮罩处理 |
| `modules/photo/` | 后期节点、参数定义、图像算法 |
| `modules/dlss/` | DLSS5 适配、固定版本部署与第三方 MIT 原生客户端 |
| `setup_dlss5.bat`、`setup_dlss5.py`、`install.py` | Windows便捷安装／环境检查与Manager安装钩子 |
| `web/` | 随整库加载的后期滑块前端 |
| `locales/zh/` | 整库中文翻译 |
| `examples/resolution/`、`examples/photo/`、`examples/contour/`、`examples/subject/` | 各功能 UI/API 示例 |
| `tests/` | 节点、算法、前端与迁移检查 |
| `scripts/` | 旧安装迁移、服务端验证工具 |
| `docs/STATUS.md` | 当前状态与后续交接入口，优先读这一份 |
| `docs/CATEGORIES.md` | 分类规范与新增节点约定 |
| `docs/history/` | 两个旧插件的历史日志和算法说明 |
