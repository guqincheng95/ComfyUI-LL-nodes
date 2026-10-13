# ComfyUI 尺寸预设节点｜需求与功能说明

## 1. 项目名称

**ComfyUI-ResolutionPreset**

目标：开发一个轻量级 ComfyUI 自定义节点，用于统一管理常用模型与常用画幅的分辨率预设，避免每次手动输入宽高、记忆尺寸参数，并方便后续统一维护 Z-Image、SCAIL-2 / WAN、FLUX 等模型的生产分辨率规范。

## 2. 核心目标

该节点不负责图像生成、不负责缩放、不负责 latent 运算，只负责：

- 根据模型家族选择预设
- 根据画面比例选择预设
- 根据质量档位选择预设
- 自动输出 `width`
- 自动输出 `height`
- 支持横竖方向切换
- 支持自定义宽高
- 所有内置生产尺寸优先遵循 32 的倍数
- 预设表与节点逻辑分离，便于后续维护

最终使用体验：

```text
Model Family: Z-Image
Ratio: 9:16
Quality Tier: Quality
Orientation: Portrait
```

自动输出：

```text
width  = 864
height = 1536
```

无需手动输入宽高，也无需记忆尺寸。

## 3. 开发原则

### 3.1 轻量

不要引入不必要的第三方依赖。优先只使用 Python 标准库和 ComfyUI 自定义节点基础接口。

不引入 CUDA 相关依赖，不引入图像处理库，不引入模型推理库。

### 3.2 稳定

节点只做“预设查表 + 数值输出”。第一版不要加入 resize、crop、pad、latent 创建、图像处理、自动超分、模型加载。

### 3.3 可维护

预设参数必须独立存放。

建议目录：

```text
ComfyUI-ResolutionPreset/
├─ __init__.py
├─ nodes.py
├─ presets.py
└─ README.md
```

其中：
- `nodes.py`：节点逻辑
- `presets.py`：全部尺寸预设
- `__init__.py`：节点注册
- `README.md`：安装说明与使用说明

后续修改尺寸时，优先只改 `presets.py`。

# 4. 第一版功能需求

## 4.1 Model Family

提供下拉选择：

```text
Z-Image
SCAIL-2 / WAN
FLUX
Custom
```

第一版只需要这四项。

## 4.2 Ratio

提供下拉选择：

```text
1:1
3:4
4:3
9:16
16:9
```

## 4.3 Quality Tier

提供：

```text
Fast
Quality
Max
```

- **Fast**：快速草图、Prompt 测试、Seed 筛选、构图测试
- **Quality**：正式生产、默认推荐档
- **Max**：原生高分辨率和极限质量测试

## 4.4 Orientation

建议加入：

```text
Auto
Portrait
Landscape
```

逻辑：
- `Auto`：严格按照 Ratio 本身输出
- `Portrait`：强制长边作为高度
- `Landscape`：强制长边作为宽度

例如：

```text
Ratio: 9:16
Quality: Quality
Portrait
```

输出：

```text
864 × 1536
```

如果切换为 `Landscape`，输出：

```text
1536 × 864
```

如果实现成本更低，也可以使用 `Swap: True / False`，但优先推荐 Orientation。

## 4.5 Custom 模式

当 `Model Family = Custom` 时，允许输入：

```text
Custom Width
Custom Height
```

并原样输出 `width / height`。

Custom 模式不得自动篡改用户输入。

可选增加 `is_32_aligned` 作为提示，但不是第一版必需项。

# 5. 第一版默认尺寸预设

## 5.1 Z-Image

当前按“32 倍数 + 1K / 1.5K / 2K 三档”建立。

### 1:1

```text
Fast     1024 × 1024
Quality  1536 × 1536
Max      2048 × 2048
```

### 3:4

```text
Fast      768 × 1024
Quality  1152 × 1536
Max      1536 × 2048
```

### 4:3

```text
Fast     1024 × 768
Quality  1536 × 1152
Max      2048 × 1536
```

### 9:16

```text
Fast      576 × 1024
Quality   864 × 1536
Max      1152 × 2048
```

### 16:9

```text
Fast     1024 × 576
Quality  1536 × 864
Max      2048 × 1152
```

说明：当前 `Quality` 作为主生产档，后续实测后可调整。所有值均为 32 的倍数。

## 5.2 SCAIL-2 / WAN

第一版先使用相同的 32 倍数框架，避免节点功能阻塞。

### 1:1

```text
Fast     1024 × 1024
Quality  1536 × 1536
Max      2048 × 2048
```

### 3:4

```text
Fast      768 × 1024
Quality  1152 × 1536
Max      1536 × 2048
```

### 4:3

```text
Fast     1024 × 768
Quality  1536 × 1152
Max      2048 × 1536
```

### 9:16

```text
Fast      576 × 1024
Quality   864 × 1536
Max      1152 × 2048
```

### 16:9

```text
Fast     1024 × 576
Quality  1536 × 864
Max      2048 × 1152
```

注意：这是第一版统一工程预设，不代表最终 SCAIL-2 最佳实测参数。完成正式工作流测试后，再单独修正 `presets.py`。

## 5.3 FLUX

第一版同样采用统一 32 倍数生产预设。

### 1:1

```text
Fast     1024 × 1024
Quality  1536 × 1536
Max      2048 × 2048
```

### 3:4

```text
Fast      768 × 1024
Quality  1152 × 1536
Max      1536 × 2048
```

### 4:3

```text
Fast     1024 × 768
Quality  1536 × 1152
Max      2048 × 1536
```

### 9:16

```text
Fast      576 × 1024
Quality   864 × 1536
Max      1152 × 2048
```

### 16:9

```text
Fast     1024 × 576
Quality  1536 × 864
Max      2048 × 1152
```

后续如果 FLUX.2 Klein 实测得出更合适的原生尺寸，再独立调整。

# 6. 节点输入输出要求

建议节点名称：

```text
Resolution Preset
```

建议分类：

```text
AI Visual / Utilities
```

或：

```text
Resolution / Presets
```

## 输入

必选：

```text
model_family
ratio
quality_tier
orientation
```

Custom 模式附加：

```text
custom_width
custom_height
```

## 输出

至少：

```text
width: INT
height: INT
```

建议：

```python
RETURN_TYPES = ("INT", "INT")
RETURN_NAMES = ("width", "height")
```

节点输出必须能直接连接到所有接受 width / height 整数输入的 ComfyUI 节点。

# 7. 交互体验要求

理想结构：

```text
Resolution Preset

Model Family
[ Z-Image ▼ ]

Ratio
[ 9:16 ▼ ]

Quality Tier
[ Quality ▼ ]

Orientation
[ Portrait ▼ ]
```

不要加入图片预览、画布、复杂 JS 前端、自定义页面。

第一版只需依赖 ComfyUI 原生节点控件。

# 8. 32 倍数规范

所有内置预设默认必须满足：

```text
width % 32 == 0
height % 32 == 0
```

建议内部加入校验：

```python
def validate_resolution(width, height):
    assert width % 32 == 0
    assert height % 32 == 0
```

Custom 模式不强制修改用户输入。

# 9. 代码结构建议

## presets.py

推荐结构：

```python
PRESETS = {
    "Z-Image": {
        "1:1": {
            "Fast": (1024, 1024),
            "Quality": (1536, 1536),
            "Max": (2048, 2048),
        },
        "9:16": {
            "Fast": (576, 1024),
            "Quality": (864, 1536),
            "Max": (1152, 2048),
        },
    },
}
```

不要把所有尺寸硬编码进节点逻辑。

## nodes.py

主要职责：
1. 获取下拉值
2. 从 `PRESETS` 查找尺寸
3. 处理 Orientation
4. 处理 Custom
5. 输出 width / height

## __init__.py

完成：

```text
NODE_CLASS_MAPPINGS
NODE_DISPLAY_NAME_MAPPINGS
```

确保 ComfyUI 自动注册节点。

# 10. 兼容性要求

必须在当前环境测试：

```text
ComfyUI 0.38.0
Python 3.12.3
PyTorch 2.9.1+cu130
RTX 4090 48GB
```

该节点本身不依赖 GPU。

必须保证：
- 不修改 Torch
- 不修改 Triton
- 不修改 SageAttention
- 不安装 xformers
- 不安装 flash-attn
- 不安装 CUDA 扩展
- 不修改 ComfyUI 核心代码

# 11. 安装方式

最终目录：

```text
ComfyUI/custom_nodes/ComfyUI-ResolutionPreset/
```

安装完成后重启 ComfyUI，应能在节点菜单中找到：

```text
Resolution Preset
```

# 12. 必须完成的测试

## Test 1

```text
Z-Image
9:16
Quality
Portrait
```

预期：

```text
864 × 1536
```

## Test 2

```text
Z-Image
16:9
Quality
Landscape
```

预期：

```text
1536 × 864
```

## Test 3

```text
Z-Image
3:4
Max
Portrait
```

预期：

```text
1536 × 2048
```

## Test 4

```text
Z-Image
4:3
Fast
Landscape
```

预期：

```text
1024 × 768
```

## Test 5

```text
Custom
Custom Width = 1376
Custom Height = 768
```

预期：

```text
1376 × 768
```

不得自动篡改 Custom 输入。

# 13. 启动验收要求

完成安装后必须启动 ComfyUI。

```bash
source /root/autodl-tmp/AI_Workspace/venvs/comfy4090/bin/activate
cd /root/autodl-tmp/AI_Workspace/ComfyUI
python main.py --listen 0.0.0.0 --port 6006
```

启动日志必须满足：

```text
无 IMPORT FAILED
无 ModuleNotFoundError
无节点相关 Traceback
```

并确认 `ComfyUI-ResolutionPreset` 成功出现在 Custom Nodes import 列表。

# 14. 工作流实测

必须创建最小测试工作流：

```text
Resolution Preset
        ↓
width / height
        ↓
任意接受宽高参数的 latent / image 节点
```

要求切换 `9:16 / 16:9 / 1:1 / 3:4 / 4:3` 均可自动改变输出尺寸。

# 15. README 要求

README 至少包含：
1. 项目用途
2. 安装路径
3. 安装方法
4. 节点位置
5. 输入说明
6. 输出说明
7. Model Family 说明
8. Ratio 说明
9. Quality Tier 说明
10. Orientation 说明
11. Custom 使用方法
12. 当前默认预设表
13. 后续如何编辑 `presets.py`

# 16. 第一版禁止事项

第一版不要做：

```text
自动下载模型
图像放大
超分
裁切
Pad
自动 resize
模型识别
工作流自动路由
LoRA
ControlNet
CUDA 加速
数据库
网络请求
云端同步
复杂 JS 前端
```

保持节点单一职责。

# 17. 后续可扩展方向

### v1.1
- 增加更多比例
- 增加 FLUX.2 Klein 专用实测预设
- 增加 SCAIL-2 专用实测预设
- 增加模型家族描述

### v1.2
- 用户自定义 `presets.json`
- 支持保存个人预设
- 支持导入 / 导出尺寸配置

### v2.0
- 结合超分节点
- 输出目标交付尺寸
- 自动计算 2x / 4x upscale 后最终尺寸

# 18. 最终交付物

工作 AI 完成后必须交付：

```text
ComfyUI-ResolutionPreset/
├─ __init__.py
├─ nodes.py
├─ presets.py
└─ README.md
```

同时提供：
1. 完整源码
2. 安装完成日志
3. ComfyUI 启动成功日志
4. 节点菜单出现证明
5. 五组测试结果
6. 最小测试工作流 JSON
7. 当前版本号

建议第一版版本：

```text
v0.1.0
```

# 19. 完成判定

只有同时满足以下条件才算完成：

```text
[ ] 节点成功注册
[ ] ComfyUI 正常启动
[ ] 无阻断错误
[ ] Z-Image 预设正确
[ ] SCAIL-2 / WAN 预设正确
[ ] FLUX 预设正确
[ ] 32 倍数校验通过
[ ] Orientation 正常
[ ] Custom 正常
[ ] width 输出正确
[ ] height 输出正确
[ ] 可连接到其他节点
[ ] README 完整
[ ] 最小测试工作流可运行
```

# 20. 给工作 AI 的执行要求

请直接完成开发，不要只给设计方案。

执行顺序：

```text
1. 创建节点目录
2. 编写 presets.py
3. 编写 nodes.py
4. 编写 __init__.py
5. 编写 README.md
6. 安装到当前 ComfyUI
7. 启动 ComfyUI
8. 检查 import
9. 创建最小测试工作流
10. 完成五组测试
11. 修复发现的问题
12. 最终交付完整源码和测试结果
```

不要重装 ComfyUI。

不要修改当前 Torch / CUDA / Triton / SageAttention 环境。

不要为了一个简单尺寸节点引入额外大型依赖。

如发现节点 API 与当前 ComfyUI 0.38.0 有兼容问题，只做最小修复。

## 最终目标

完成一个轻量、稳定、可长期维护的 ComfyUI 分辨率预设节点，作为后续 Z-Image、SCAIL-2 / WAN、FLUX 等视觉工作流的统一尺寸入口。

核心体验：

```text
选模型
→ 选比例
→ 选质量档
→ 自动输出宽高
```

不再手动记忆和输入常用分辨率。
