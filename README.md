# comfyui-LL-nodes · LL 个人节点库

**v0.4.0** · 一个目录安装 · 一次更新全部节点 · 中文分类与搜索

| ComfyUI 分类 | 节点 | 功能 |
|---|---|---|
| LL 节点库 / 图像工具 / 尺寸与比例 | LL 比例预设 | 6 种比例、3 档尺寸、方向与自定义宽高；含 2:3 |
| LL 节点库 / 图像工具 / 人物轮廓 | LL 人物轮廓修剪 | 结合原图前景与骨架裁掉头饰、裙摆等外扩深度；支持批量和对比预览 |
| LL 节点库 / 图像后期 / 基础调色 | LL 后期修图 | 光影六项、白平衡、饱和度、三明度区域色彩平衡；19 项滑块及数值微调 |

新增人物轮廓修剪的接线与参数说明见 [CONTOUR_TRIM.md](docs/CONTOUR_TRIM.md)，示例在 `examples/contour/`。

搜索 `LL` 查看本库节点，也可搜索“比例预设”“后期修图”“曝光”“白平衡”或原英文名称。
旧工作流使用的 `ResolutionPreset`、`AIVisualPhotoFinish` 类型标识保持不变，连接和参数顺序保持兼容。

## 首次安装

在 ComfyUI 根目录执行：

```bash
git clone https://github.com/guqincheng95/ComfyUI-LL-nodes.git custom_nodes/comfyui-LL-nodes
```

也可把交付 ZIP 上传至 `custom_nodes` 后解压，最终入口为 `custom_nodes/comfyui-LL-nodes/__init__.py`。不要把 `modules` 中的文件夹单独安装。

只使用 ComfyUI 已有的 PyTorch；无模型下载、无额外 pip 安装步骤。

## 从两个独立插件迁移（只需一次）

停止 ComfyUI 后，把 `comfyui-LL-nodes-v0.4.0.zip` 上传至 `custom_nodes`：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes
python -m zipfile -e comfyui-LL-nodes-v0.4.0.zip .
python comfyui-LL-nodes/scripts/migrate_legacy.py --apply
```

迁移脚本将已识别的旧 `ComfyUI-ResolutionPreset`、`ComfyUI-PhotoFinish`（含 `-main`）目录移到 ComfyUI 根目录的 `ll-nodes-backups/时间戳/`，不删除旧文件。避免新旧插件同时注册同名节点。其他改过名字的旧目录需要自行移到 `custom_nodes` 外。

若过去手工修改过 `presets.py`，自定义内容仍在备份中，可按需合并到新版 `modules/resolution/presets.py`；脚本不会擅自覆盖新版预设。

重启 ComfyUI，界面语言选择中文，浏览器 Ctrl+F5。旧节点若曾手工改标题会保留原标题；新建节点可看到 LL 名称。

## 后续统一更新

Git 安装：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes/comfyui-LL-nodes
git pull --ff-only
```

ZIP 安装：下载新的整库 ZIP 并在 `custom_nodes` 覆盖解压。ZIP 安装不包含 Git 历史，不能直接 git pull。两种方式都会同时更新比例预设、后期修图、前端和翻译，最后重启并刷新。

若原比例插件目录本身是 Git 克隆，也可以直接在原目录更新；新的入口会同时加载两个节点。随后运行该目录的 `scripts/migrate_legacy.py --apply` 移走独立后期插件。目录重命名不是工作流兼容的前提。

## 目录与文档

| 路径 | 用途 |
|---|---|
| `__init__.py` | 整库唯一节点注册入口与版本 |
| `modules/resolution/` | 尺寸与比例节点、预设表 |
| `modules/contour/` | 人物轮廓、关键点适配和遮罩处理 |
| `modules/photo/` | 后期节点、参数定义、图像算法 |
| `web/` | 随整库加载的后期滑块前端 |
| `locales/zh/` | 整库中文翻译 |
| `examples/resolution/`、`examples/photo/`、`examples/contour/` | 各功能 UI/API 示例 |
| `tests/` | 节点、算法、前端与迁移检查 |
| `scripts/` | 旧安装迁移、服务端验证工具 |
| `docs/STATUS.md` | 当前状态与后续交接入口，优先读这一份 |
| `docs/CATEGORIES.md` | 分类规范与新增节点约定 |
| `docs/history/` | 两个旧插件的历史日志和算法说明 |

本版新增人物轮廓修剪；比例、后期调色和滑块保留。尚未在用户实际 ComfyUI 服务端进行安装与界面联调。验证记录见 `docs/TEST_REPORT.md`。
