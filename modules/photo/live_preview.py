"""Opt-in, bounded preview data for the browser; no temporary image files."""
import base64
import zlib

MAX_SIDE = 640


def preview_result(result, enabled, base, manual, automatic):
    if not enabled:
        return result
    import torch
    import torch.nn.functional as F

    frame = base[0].detach().permute(2, 0, 1).unsqueeze(0).to(device='cpu', dtype=torch.float32)
    h, w = frame.shape[-2:]
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        size = max(1, round(h * scale)), max(1, round(w * scale))
        if frame.shape[1] == 4:
            frame = torch.cat((frame[:, :3] * frame[:, 3:], frame[:, 3:]), dim=1)
        frame = F.interpolate(frame, size=size, mode='bilinear', align_corners=False, antialias=True)
        if frame.shape[1] == 4:
            frame = torch.cat((frame[:, :3] / frame[:, 3:].clamp_min(1e-8), frame[:, 3:]), dim=1)
    if frame.shape[1] == 3:
        frame = torch.cat((frame, torch.ones_like(frame[:, :1])), dim=1)
    pixels = frame[0].permute(1, 2, 0).clamp(0, 1).mul(65535).round().numpy().astype('<u2')
    data = base64.b64encode(zlib.compress(pixels.tobytes(), level=1)).decode('ascii')
    payload = {'version': 1, 'width': pixels.shape[1], 'height': pixels.shape[0], 'pixels': data,
               'batch': base.shape[0], 'manual': manual, 'automatic': automatic}
    return {'ui': {'ll_photo_preview': [payload]}, 'result': result}
