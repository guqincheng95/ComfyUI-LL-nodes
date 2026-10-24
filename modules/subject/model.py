"""Local SAM 2.1 adapter. No downloads, persistent GPU cache or package installs."""
import os
from pathlib import Path

MODELS={
 'sam2.1_hiera_tiny.pt':'configs/sam2.1/sam2.1_hiera_t.yaml',
 'sam2.1_hiera_small.pt':'configs/sam2.1/sam2.1_hiera_s.yaml',
 'sam2.1_hiera_base_plus.pt':'configs/sam2.1/sam2.1_hiera_b+.yaml',
 'sam2.1_hiera_large.pt':'configs/sam2.1/sam2.1_hiera_l.yaml',
}
SEMANTIC_FILE='deeplabv3_mobilenet_v3_large-fc3c493d.pth'


def load_semantic(device):
    import torch
    checkpoint=model_directory()/SEMANTIC_FILE
    if not checkpoint.is_file():raise RuntimeError(f'缺少人物语义模型：{checkpoint}。见docs/SUBJECT_SETUP.md；不会自动下载。')
    try:
        from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large
    except ImportError as exc:raise RuntimeError('缺少匹配当前Torch的torchvision，见docs/SUBJECT_SETUP.md。') from exc
    model=deeplabv3_mobilenet_v3_large(weights=None,weights_backbone=None,aux_loss=True)
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True))
    return model.to(device).eval()


def semantic_probability(model,rgb):
    import torch
    device=next(model.parameters()).device
    x=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].to(device)
    mean=x.new_tensor([.485,.456,.406])[None,:,None,None]
    std=x.new_tensor([.229,.224,.225])[None,:,None,None]
    with torch.inference_mode():return model((x-mean)/std)['out'].softmax(1)[0,15].cpu().numpy()


def model_directory():
    if os.environ.get('LL_SAM2_MODEL_DIR'):return Path(os.environ['LL_SAM2_MODEL_DIR'])
    try:
        import folder_paths
        return Path(folder_paths.models_dir)/'sam2'
    except ImportError:
        return Path(__file__).resolve().parents[4]/'models'/'sam2'


def load_predictor(name,device):
    if name not in MODELS:raise ValueError('未知SAM2.1模型。')
    checkpoint=model_directory()/name
    if not checkpoint.is_file():
        raise RuntimeError(f'缺少本地模型：{checkpoint}。请按docs/SUBJECT_SETUP.md安装；节点不会自动下载。')
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError as exc:
        raise RuntimeError('SAM2或其依赖未安装。请按docs/SUBJECT_SETUP.md配置，或选择external_mask模式。') from exc
    return SAM2ImagePredictor(build_sam2(MODELS[name],str(checkpoint),device=device,apply_postprocessing=False))


def predict(predictor,rgb,positive,negative,box,hint=None,semantic=None):
    import numpy as np
    import torch
    from .prompts import select_candidate
    points=np.concatenate([positive,negative]);labels=np.r_[np.ones(len(positive)),np.zeros(len(negative))].astype(np.int32)
    with torch.inference_mode():
        predictor.set_image(np.rint(rgb*255).astype(np.uint8))
        prior=None
        if semantic is not None:
            from torch.nn import functional as F
            probability=F.interpolate(torch.from_numpy(semantic.copy())[None,None],size=(256,256),mode='bilinear',align_corners=False)[0].clamp(.01,.99)
            prior=torch.logit(probability).numpy()
        masks,scores,_=predictor.predict(point_coords=points,point_labels=labels,box=box,mask_input=prior,multimask_output=True)
    return select_candidate(masks,scores,positive,negative,hint)
