"""ComfyUI adapter; no heavyweight dependency is imported at registration time."""


class PersonContourTrim:
    @classmethod
    def INPUT_TYPES(cls):
        required = {
            'depth_image': ('IMAGE', {'tooltip': '连接 Depth Anything V2 的原始深度图，在与骨架图混合之前修剪。'}),
            'keypoints': ('POSE_KEYPOINT', {'tooltip': '连接 SDPoseKeypointExtractor 或 DWPose 的关键点输出，不是骨架图片。'}),
        }
        for name, label in [('head_scale', '头部'), ('torso_scale', '躯干'), ('arm_scale', '手臂'), ('leg_scale', '腿部')]:
            required[name] = ('FLOAT', {'default': 1.0, 'min': 0.4, 'max': 2.0, 'step': 0.05,
                                      'tooltip': f'{label}轮廓宽度倍率；小于 1 收紧，大于 1 放宽。'})
        required.update({
            'padding_px': ('INT', {'default': 4, 'min': 0, 'max': 64, 'step': 1, 'tooltip': '额外保留边缘像素，避免误切；过大会留下装饰。'}),
            'feather_px': ('INT', {'default': 2, 'min': 0, 'max': 32, 'step': 1, 'tooltip': '向保留区域内部柔化边缘；设 0 使用硬边。'}),
            'confidence': ('FLOAT', {'default': 0.3, 'min': 0.0, 'max': 1.0, 'step': 0.05}),
            'temporal_smoothing': ('FLOAT', {'default': 0.0, 'min': 0.0, 'max': 0.9, 'step': 0.05,
                'tooltip': '连续单人视频可设 0.2～0.3，平滑关键点而非混合遮罩；独立图片设 0。只在当前批次内生效。'}),
            'person_index': ('INT', {'default': 0, 'min': -1, 'max': 99, 'step': 1,
                'tooltip': '0 为第一人，-1 保留全部检测人物。多人不进行时间平滑。'}),
            'background_value': ('FLOAT', {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 0.01,
                'tooltip': '裁掉区域填充值；通常为 0（黑）。按后续深度条件的约定设置。'}),
            'coordinate_mode': (['auto', 'pixels', 'normalized'], {'default': 'auto'}),
            'missing_pose': (['keep', 'error'], {'default': 'keep',
                'tooltip': '关键点不足时保留原帧并输出说明，或中止报错，避免把身体误剪掉。'}),
        })
        return {'required': required, 'optional': {
            'foreground_mask': ('MASK', {'tooltip': '推荐：原图经 BEN2 等背景移除得到的 MASK（白色为保留）。必须与深度图同裁切；等比例分辨率自动对齐，支持单帧或逐帧。'}),
            'protect_mask': ('MASK', {'tooltip': '可选：手脚、正常头发等需要额外保留的白色区域；可接成熟人体分割节点的部位遮罩。'}),
            'exclude_mask': ('MASK', {'tooltip': '可选：帽子、头饰等需要明确裁掉的白色区域；最后执行，优先于保留遮罩。'}),
            'foot_protection': ('BOOLEAN', {'default':True, 'tooltip':'独立保护完整脚掌／鞋；建议连接前景MASK约束边界。'}),
            'foot_scale': ('FLOAT', {'default':1.2, 'min':.5, 'max':3., 'step':.05, 'tooltip':'脚掌保护范围倍率，不改变小腿倍率；近镜头大脚、长鞋可增加。'}),
            'hand_protection': ('BOOLEAN', {'default':True, 'tooltip':'独立保护手掌／手指；有21点手部关键点时按完整轮廓构造范围。'}),
            'hand_scale': ('FLOAT', {'default':1.15, 'min':.5, 'max':3., 'step':.05, 'tooltip':'手掌保护范围倍率，不改变手臂倍率。'}),
        }}

    RETURN_TYPES = ('IMAGE', 'MASK', 'IMAGE', 'STRING')
    RETURN_NAMES = ('trimmed_depth', 'keep_mask', 'overlay_preview', 'report')
    FUNCTION = 'trim'
    CATEGORY = 'LL 节点库/图像工具/人物轮廓'
    DESCRIPTION = '修剪头饰、裙摆、宽袖等外扩轮廓；结合原图前景与骨架，保留区域使用原深度。不补全身体、不生成新深度。'

    def trim(self, depth_image, keypoints, foreground_mask=None, protect_mask=None, exclude_mask=None, **options):
        import torch
        import warnings
        from .processing import build_masks, validate_options
        opts = validate_options(options)
        if not isinstance(depth_image, torch.Tensor) or depth_image.ndim != 4 or depth_image.shape[-1] not in (3, 4):
            raise ValueError('depth_image 必须是 [B,H,W,3或4] 的 ComfyUI IMAGE。')
        if not depth_image.is_floating_point() or not torch.isfinite(depth_image).all() or depth_image.numel() == 0:
            raise ValueError('深度图必须为非空有限浮点图像。')
        if depth_image.min() < 0 or depth_image.max() > 1:
            raise ValueError('深度图范围必须为 0～1。')
        b, h, w, _ = depth_image.shape
        masks = {}
        for name, value in [('foreground_mask', foreground_mask), ('protect_mask', protect_mask), ('exclude_mask', exclude_mask)]:
            if value is not None:
                if not isinstance(value, torch.Tensor):
                    raise ValueError(f'{name} 必须是 ComfyUI MASK。')
                masks[name] = value.detach().float().cpu().numpy()
        array, report = build_masks(keypoints, b, h, w, **masks, **opts)
        if '帧未修剪' in report:
            warnings.warn(report, RuntimeWarning, stacklevel=2)
        keep = torch.from_numpy(array).to(device=depth_image.device)
        blend = keep.to(dtype=depth_image.dtype)[..., None]
        with torch.no_grad():
            result = depth_image.clone()
            result[..., :3] = depth_image[..., :3] * blend + opts['background_value'] * (1 - blend)
            if result.shape[-1] == 4:
                result[..., 3] = depth_image[..., 3] * keep.to(dtype=depth_image.dtype)
            # Green = kept; red = removed non-background. The original depth is never quantized.
            preview = depth_image[..., :3].clone()
            occupied = (depth_image[..., :3] - opts['background_value']).abs().amax(dim=-1, keepdim=True) > 0.01
            color = torch.zeros_like(preview)
            color[..., 1] = blend[..., 0]
            color[..., 0] = (1 - blend[..., 0]) * occupied[..., 0]
            preview = torch.where(occupied, preview * 0.55 + color * 0.45, preview)
        return result, keep, preview, report
