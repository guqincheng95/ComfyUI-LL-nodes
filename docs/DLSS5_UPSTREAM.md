# DLSS5 来源与适配边界

- 源项目：https://github.com/Blueforcer/ComfyUI-DLSS5-Enhancer
- 固定来源提交：`796ed5927a202ba50b5c929cd08e16b365041162`。
- 复制的 MIT 客户端位于 `modules/dlss/native/`：paths、session、settings、protocol、imaging、motion、diagnostics；许可证全文见 [Blueforcer-DLSS5-MIT.txt](licenses/Blueforcer-DLSS5-MIT.txt)。没有复制原项目V3节点注册、视频编码层或安装器。
- LL 修改：运行时路径隔离到仓库忽略的 `runtime/dlss5/`；路径配置原子写入；新增I/O超时与取消看门狗；GPU识别支持部分专业卡并跳过不支持的候选。专业卡能识别不等于底层兼容已验证。
- LL 新代码：稳定V1节点、一次整图渲染的线性光分区融合、统一光影近似分离、边缘控制、同位置中性色／皮肤色度保护、光流遮罩稳定、ROI对比，以及固定版本SHA256安装脚本。
- 第三方运行时：https://github.com/Merserk/dlss5-visual-enhancer/releases/tag/v3.0 ，发布资产SHA256固定在 `runtime_setup.py`；是该项目发布包，不称为NVIDIA官方安装包。
- NVIDIA、ReShade、RenoDX及上游worker的二进制遵守各自条款，非本库授权范围；本库不分发二进制、不重分发神经网络权重。使用者按各组件条款使用。
- 技术边界参考：https://developer.nvidia.com/blog/whats-new-for-game-developers-dlss-5-with-3d-guided-neural-rendering-nvidia-ace-updates-and-new-rtx-kit-capabilities/ 。官方引擎层遮罩能力不代表当前社区协议已暴露外部MASK接口。
- 安装钩子约定：https://github.com/Comfy-Org/ComfyUI-Manager ，标准流程安装时调用 `install.py`；单纯git更新／ZIP覆盖不会执行该脚本。
