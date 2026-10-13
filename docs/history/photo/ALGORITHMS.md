# 算法选型与来源检查

调研日期：2026-10-10。先检查现有开源源码，再选择适合轻量 ComfyUI 插件的实现。

## 实际检查过的项目

1. [ComfyUI_LayerStyle](https://github.com/chflame163/ComfyUI_LayerStyle)，MIT。
   - `py/color_correct_exposure.py`：曝光倍乘，特殊负曝光处理。
   - `py/color_correct_color_balance.py` 和 `py/imagefunc.py`：通道曲线、亮度比率恢复。
   - `tensor2pil` 会量化成 uint8；本项目避免走这一中间路径。
   - 三点样条按各通道值处理，与我们按整体亮度分区的目标不同。
2. [GPUImage2](https://github.com/BradLarson/GPUImage2)，BSD 3-Clause 风格许可证（License.txt）。
   - `framework/Source/Operations/Shaders/Exposure_GL.fsh`：2^EV。
   - `WhiteBalance_GL.fsh`：YIQ 与暖色叠加。
   - `HighlightShadow_GL.fsh`：亮度幂函数与亮度比例重建。
   - `Vibrance_GL.fsh`：依据通道差异调节色彩。
3. [darktable exposure.c](https://github.com/darktable-org/darktable/blob/master/src/iop/exposure.c)，GPL-3.0-or-later。
   - 查阅曝光定义及许可证。没有移植 darktable 代码或引入其完整 RAW 管线。

上述调研不代表引用了整套 Camera Raw 算法。项目没有复制这些项目的源码段落；使用通用曝光关系、sRGB 传递函数与独立实现的区域曲线。没有引入 SciPy/OpenCV 或 RAW 解码依赖。

## 处理定义

1. 以标准分段 sRGB 传递函数解码至线性 RGB。
2. 相对色温/色调：通道指数增益，以线性 Y 权重归一化中性灰增益。这是相对偏色工具，不是相机 RAW 白平衡标定。
3. 曝光：线性 RGB 乘 2^EV。
4. 取线性 Y（0.2126R+0.7152G+0.0722B），编码成感知亮度以调整光影。
   - 对比度：对称幂曲线。
   - 阴影：0～0.55 范围的平滑多项式调整，保留纯黑端点。
   - 高光：0.45～1 范围的平滑多项式调整，保留纯白端点。
   - 黑色/白色：smoothstep 调整两端黑白位，因此与阴影/高光不同。
   - 组合极值测试确保灰阶曲线不反转。非局部自适应算法，无空间模糊产生的光晕。
5. 三明度区使用 smoothstep 连续权重，权重之和为 1，避免硬阈值接缝。色彩平衡使用整体亮度确定区域，不使用单个颜色通道值划区。
6. 保持明度：减去新增色度的 Y 分量；超色域时向同亮度中性灰压缩，保持线性 Y。不是 CIELAB L* 或 Photoshop 专有“保留明度”算法。
7. 自然饱和度：依相对通道跨度降低高饱和区域的正向增益；普通饱和度统一缩放色度。无肤色识别算法。
8. 编码回 sRGB float32 [0,1]。

## 明确局限

曝光推到显示白以上的数据在进入光影曲线时按显示范围处理，不提供 RAW 高光恢复。大幅提曝光产生的截断不能靠后续高光滑块完整救回，应先降低曝光。
纯黑用阴影滑块不会凭空生出纹理；黑位滑块可以抬灰。色温不会以摄影机 Kelvin 值给出。
效果验证不包含与 Adobe 的逐像素匹配，不作“达到几成 Camera Raw”的声明。
