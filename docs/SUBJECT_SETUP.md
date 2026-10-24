# v0.6 增强人物节点安装

旧比例、调色、人物轮廓节点继续使用原依赖。只有新增 `LLPersonSubjectClean` 需要本说明中的额外依赖和模型。节点运行时不安装软件、不联网下载权重；缺少文件会明确报错。

## 1. 使用运行 ComfyUI 的 Python

用户现有环境示例（实际路径不同请对应替换）：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes/comfyui-LL-nodes
/root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/python -m pip install -r requirements-subject.txt
/root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

如果已有可正常导入的 torchvision，无需重装。SAM2官方要求 Python≥3.10、Torch≥2.5.1、torchvision≥0.20.1。torchvision 必须匹配已安装 Torch；不要为本插件整体升级 Torch/CUDA。对于此前确认的 **Torch 2.9.1+cu130**，配套为 torchvision 0.24.1，缺少时可安装：

```bash
/root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/python -m pip install --no-deps torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu130
```

其他 Torch/CUDA 版本按 [PyTorch 官方对应表](https://pytorch.org/get-started/previous-versions/) 选择，不能照抄此版本。

## 2. 安装 SAM2 源码

本版实际验证的上游提交为 `2b90b9f5ceec907a1c18123530e92e794ad901a4`。在 `custom_nodes` **外**准备源码目录：

```bash
cd /root/autodl-tmp/AI_Workspace
git clone https://github.com/facebookresearch/sam2.git sam2-source
cd sam2-source
git checkout 2b90b9f5ceec907a1c18123530e92e794ad901a4
SAM2_BUILD_CUDA=0 /root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/python -m pip install --no-deps --no-build-isolation .
```

这里禁用可选 CUDA 扩展编译，避免要求 nvcc；模型仍可在 CUDA 上推理。依赖已经在上一步准备，`--no-deps` 避免安装过程替换用户 Torch。若缺少构建工具，可单独安装 `setuptools`、`wheel`。

服务器访问GitHub困难时，在电脑下载[该提交的源码ZIP](https://github.com/facebookresearch/sam2/archive/2b90b9f5ceec907a1c18123530e92e794ad901a4.zip)，上传到 `AI_Workspace`：

```bash
cd /root/autodl-tmp/AI_Workspace
python -m zipfile -e sam2-2b90b9f5ceec907a1c18123530e92e794ad901a4.zip .
cd sam2-2b90b9f5ceec907a1c18123530e92e794ad901a4
SAM2_BUILD_CUDA=0 /root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/python -m pip install --no-deps --no-build-isolation .
```

下载后的文件名可能不同，解压命令使用实际文件名。PyPI依赖可以使用可访问的pip源；不要把未经校验的模型镜像混作Python依赖源。

## 3. 放入两份默认模型

推荐组合 `semantic_sam2`：轻量 DeepLabV3 MobileNetV3 人物语义引导 + SAM2.1 Tiny。两份权重合计约200 MB，ZIP代码包不包含权重。

| 文件名 | 官方下载 | 放置位置 |
|---|---|---|
| `sam2.1_hiera_tiny.pt` | [Meta](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt) | `ComfyUI/models/sam2/` |
| `deeplabv3_mobilenet_v3_large-fc3c493d.pth` | [PyTorch](https://download.pytorch.org/models/deeplabv3_mobilenet_v3_large-fc3c493d.pth) | `ComfyUI/models/sam2/` |

可在电脑下载后上传。检查文件（不联网）：

```bash
cd /root/autodl-tmp/AI_Workspace/ComfyUI/custom_nodes/comfyui-LL-nodes
python scripts/subject_models.py
```

若服务器可访问官方源，可显式下载并校验：

```bash
python scripts/subject_models.py --download
```

支持 `--directory` 自定义检查目录；下载可用 `--sam-url HTTPS完整地址 --person-url HTTPS完整地址` 指定镜像，两份文件仍按内置 SHA256 和大小验证。失败不会覆盖已有权重。节点自定义模型目录通过启动环境变量 `LL_SAM2_MODEL_DIR` 设置。

SAM2 Small／Base+／Large 可按 [SAM2 官方说明](https://github.com/facebookresearch/sam2#download-checkpoints) 自行安装到同目录，并在节点选择对应文件；本版真实推理验证的是 Tiny。仅 `sam2` 模式不用语义模型，但更依赖提示质量，不作为推荐默认。`external_mask` 模式不加载任何模型，只需SciPy和现有依赖。

重启 ComfyUI，浏览器 Ctrl+F5，搜索“LL 人物主体提取”。接线及限制见 [SUBJECT_CLEAN.md](SUBJECT_CLEAN.md)。
