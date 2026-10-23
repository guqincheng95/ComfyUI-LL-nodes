# 自动色彩匹配：技术采用记录

v0.5.0 优先查阅已有实现和作者资料，再按本库的 PyTorch IMAGE 接口实现。运行时沿用现有 PyTorch，不增加模型、OpenCV、scikit-image 或 color-matcher 安装依赖。

| 查阅来源 | 借鉴 / 采用 |
|---|---|
| [scikit-image 官方直方图匹配示例](https://scikit-image.org/docs/stable/auto_examples/color_exposure/plot_histogram_matching.html) | 累积分布／分位数映射思路。本实现仅在感知明度上做单调映射，颜色另行处理。 |
| [color-matcher 仓库](https://github.com/hahnec/color-matcher) 的 `reinhard_matcher.py`、`hist_matcher.py` 与许可证 | 对比成熟的均值／标准差颜色迁移与直方图匹配路线；该库为 GPL-3.0，本项目未复制其代码，也不依赖该库。 |
| [Björn Ottosson 的 Oklab 原作者说明](https://bottosson.github.io/posts/oklab/) | 使用其 2021 年更新的线性 sRGB ↔ Oklab 矩阵；原作者提供的相关代码可按公有领域使用，源码已注明出处。 |

## 本项目中的组合

- **同画面原图对齐**：把两图采样到同一小画布，在可见、未明显裁切的像素中，用带恒等正则的 Huber 迭代加权拟合线性 RGB 仿射变换。只估计整体颜色关系，完整图像的纹理取自待调图。
- **不同图片参考仿色**：在 Oklab 中，用 129 个明度分位点构建单调映射；阴影、中间调、高光分别估计颜色均值和标准差，使用平滑区域权重融合。限制颜色方差增益，弱化纯黑／纯白端的颜色偏移，避免数值不稳定与明显染色。
- **强度控制**：将匹配结果与输入在 Oklab 的明度、颜色维度分别混合，再使用既有色域压缩。自动处理后接原手动算法。
- **工程处理**：统计采样最长边 256，RGBA 缩小时预乘 Alpha，完整尺寸分行处理，单参考批量广播，输入验证及中文错误提示；无额外学习模型。

此实现匹配全图统计，不进行语义区域对应、局部形变校正、ICC 色彩管理或 RAW 显影。后续若要加入肤色保护或选区匹配，需要另行设计遮罩与区域权重。
