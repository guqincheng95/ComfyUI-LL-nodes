# ComfyUI-ResolutionPreset

**v0.1.1** · 轻量分辨率预设节点 · Python 标准库 · 无运行时网络请求

选模型 → 选比例 → 选质量 → 输出 `width` / `height` 两个 `INT`，直接连接需要宽高的节点。
仅提供尺寸，不生成图像、不处理 latent、不缩放、不加载模型。无需 pip 安装依赖，也不会修改 Torch、CUDA、Triton、SageAttention 或 ComfyUI 核心代码。

## 安装与更新

在你的 **ComfyUI 根目录**运行：

```bash
git clone https://github.com/guqincheng95/ComfyUI-ResolutionPreset.git custom_nodes/ComfyUI-ResolutionPreset
```

也可以下载 GitHub 源码 ZIP，解压并重命名为 `ComfyUI-ResolutionPreset`，确保目录不是双层嵌套：

```text
ComfyUI/custom_nodes/ComfyUI-ResolutionPreset/__init__.py
```

重启 ComfyUI 后，搜索 **Resolution Preset**，或在 **AI Visual / Utilities** 中添加。
更新：在插件目录执行 `git pull --ff-only`，再重启 ComfyUI。卸载只需移除插件目录后重启。

## 输入与输出

| 输入 | 可选项 / 默认值 | 行为 |
|---|---|---|
| model_family | Z-Image（默认）、SCAIL-2 / WAN、FLUX、Custom | 选择独立的模型预设表 |
| ratio | 1:1、3:4、4:3、9:16（默认）、16:9、2:3 | 宽:高 |
| quality_tier | Fast、Quality（默认）、Max | 快速草图 / 正式生产 / 原生高分辨率测试 |
| orientation | Auto（默认）、Portrait、Landscape | 保持比例方向 / 长边为高 / 长边为宽 |
| custom_width | 1376 | Custom 宽度，正整数，步长 1 |
| custom_height | 768 | Custom 高度，正整数，步长 1 |

输出端口依次是 `width: INT`、`height: INT`。目标节点如果宽高仍是数值控件，右键将对应控件转换为输入，再连线。
参数变化后的输出在下一次执行工作流时生效；节点本身不增加实时预览或复杂前端。

### 模型家族

Z-Image、SCAIL-2 / WAN、FLUX 在本版使用相同尺寸规范，但各自的表完全独立，后续可单独调整。
这些是用户定义的工程预设，尤其 SCAIL-2 / WAN 和 FLUX **尚非模型最佳尺寸实测结论**。Max 表示更大输入尺寸，不保证模型质量一定提高；显存占用由下游工作流决定。

### 方向

- Auto：严格保持所选 Ratio 的宽高方向。
- Portrait：较短的一边作为宽、较长的一边作为高。
- Landscape：较长的一边作为宽、较短的一边作为高。
- 1:1 在任何方向下都保持正方形。

例如 Z-Image / 9:16 / Quality：Auto、Portrait 输出 `864 × 1536`；Landscape 输出 `1536 × 864`。

### Custom

选择 Custom 后，直接使用 custom_width / custom_height。**Ratio、Quality Tier 和 Orientation 均被忽略**，不交换宽高、不取整、不补齐 32 倍数。例如 `1377 × 769` 保持原值。
原生控件始终可见；非 Custom 模式忽略两项自定义值。范围为 1..2147483647，节点只输出整数，实际可用尺寸受下游节点及资源限制。

## 默认预设表

以下表分别用于 Z-Image、SCAIL-2 / WAN、FLUX；表中均为宽 × 高，所有内置值都是 32 的倍数。

| 比例 | Fast | Quality | Max |
|---|---|---|---|
| 1:1 | 1024 × 1024 | 1536 × 1536 | 2048 × 2048 |
| 3:4 | 768 × 1024 | 1152 × 1536 | 1536 × 2048 |
| 4:3 | 1024 × 768 | 1536 × 1152 | 2048 × 1536 |
| 9:16 | 576 × 1024 | 864 × 1536 | 1152 × 2048 |
| 16:9 | 1024 × 576 | 1536 × 864 | 2048 × 1152 |
| 2:3 | 704 × 1056 | 1024 × 1536 | 1344 × 2016 |

## 修改预设

尺寸均在 `presets.py`，节点逻辑在 `nodes.py`，注册在 `__init__.py`。
修改 `_BASE` 会改变三类模型的初始表。只调整一个模型时，在 `PRESETS` 创建之后、最后一行 `validate_presets()` 之前添加：

```python
PRESETS["FLUX"]["9:16"]["Quality"] = (864, 1536)
PRESETS["FLUX"]["16:9"]["Quality"] = (1536, 864)
```

正反比例应一起维护。保留全部比例和档位；尺寸必须为正整数且能被 32 整除。无效预设会在导入时报告具体模型、比例或档位。改完重启 ComfyUI。

## 工作流与测试

将 [`examples/minimal_workflow.json`](examples/minimal_workflow.json) 拖入 ComfyUI：

**Resolution Preset → EmptyImage → SaveImage**

使用内置空图节点承接两个整数，保存纯色测试图以验证实际尺寸；不用模型或 VAE。SaveImage 是执行终点，避免只有 latent 节点但无输出节点导致工作流不执行。切换六种比例并运行即可检查尺寸。
`examples/minimal_api.json` 是同一工作流的 API 格式，供验收脚本使用。

纯 Python 测试（无需 ComfyUI）：

```bash
cd ComfyUI/custom_nodes/ComfyUI-ResolutionPreset
python -m unittest discover -s tests -v
```

已覆盖需求五例、全部 162 个内置方向组合、Custom 不对齐值、错误输入、预设校验、注册声明和工作流连线结构。

**目标环境验收尚待执行**：当前开发容器是 Python 3.12.14，没有指定的 ComfyUI 0.38.0 / Python 3.12.3 / PyTorch 2.9.1+cu130 / RTX 4090 48GB 环境。未将单元测试冒充 ComfyUI 启动或 UI 验收。完整步骤见 [验收说明](docs/ACCEPTANCE.md)，当前证据见 [测试报告](docs/TEST_REPORT.md)。

## 文件结构

```text
__init__.py                  节点注册与版本号
nodes.py                     控件、方向和 Custom 逻辑
presets.py                   独立预设表与校验
examples/minimal_workflow.json  可拖入 UI 的工作流
examples/minimal_api.json       API 工作流
scripts/verify_server.py        可选的目标环境验收工具
scripts/capture_startup.sh      按用户指定路径启动并留存真实日志
tests/test_resolution.py        标准库测试
docs/                         需求、测试、验收、开发与交接记录
```

验收脚本仅在手动运行时向指定的 ComfyUI 服务发起请求；节点运行本身没有网络请求。
后续更多比例、JSON 预设导入导出、超分等不属于本次需求规定的版本范围。

## Krea 2 与 2:3（v0.1.1）

Krea 2 官方 README 说明输出宽高不足 16 倍数时向上补齐；当前插件所有预设均为 32 倍数，因此也符合该网格。按用户要求不新增 Krea 2 模型选项，可选择 Z-Image 表输出宽高连接 Krea 2 工作流；这仅复用尺寸，不切换实际模型。

2:3：Fast 704×1056、Quality 1024×1536、Max 1344×2016。保持精确 2:3 和两边都为 32 倍数，长边取最接近原有 1024/1536/2048 档的可用值。Landscape 输出反向 3:2，无需另加比例。

官方区分 Raw（训练到约 1K）和 Turbo（说明可生成 1K～2K）；不要把网格兼容理解为所有档位都是最佳实测参数。Raw 可先试 Fast；Turbo 可试 Quality，再按显存、耗时和效果决定是否使用 Max。本次没有运行 Krea 2 模型进行画质测试。

来源：https://github.com/krea-ai/krea-2 ，README blob `6dc93f45bcb7d7afac00c342bbc8b67417ee03c2`，查询日期 2026-10-10。

### ZIP 更新

v0.1.1 ZIP 只包含尺寸插件，不含独立的 PhotoFinish 插件。若曾修改 presets.py 请先备份；解压覆盖同名文件后重启 ComfyUI，再刷新浏览器。旧的五种比例及预设数值保持不变。
