"""Optional local ATR human parsing via ONNX Runtime; never downloads a model.

Model: mattmdjaga/segformer_b2_clothes (18 ATR classes). The separately
downloaded weights retain their NVIDIA SegFormer research/evaluation license.
This adapter does not redistribute upstream model code or weights.
"""
import os
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

BODY_IDS=(2,9,10,11,12,13,14,15)
GARMENT_IDS=(4,5,7,17)


def model_path():
    if os.environ.get('LL_PARTS_MODEL'):
        return Path(os.environ['LL_PARTS_MODEL'])
    from .model import model_directory
    root=model_directory().parent/'segformer_b2_clothes'
    for path in (root/'onnx/model.onnx',root/'model.onnx'):
        if path.is_file():return path
    return root/'onnx/model.onnx'


def load_parser():
    path=model_path()
    if not path.is_file():
        raise RuntimeError(f'缺少本地人体部位ONNX模型：{path}。见docs/SUBJECT_PRUNING.md；不会自动下载。')
    from ...scripts.subject_models import verify
    from ...scripts.setup_subject_pruning import MODEL_SIZE,MODEL_SHA256
    if not verify(path,MODEL_SIZE,MODEL_SHA256):
        raise RuntimeError('人体部位ONNX大小／SHA256不符，不能把其他18类模型直接当作ATR模型；请运行配置脚本校验。')
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError('语义剪枝需要onnxruntime，或改选external_masks接已有部位MASK；见docs/SUBJECT_PRUNING.md。') from exc
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])


def probabilities(session,rgb):
    image=Image.fromarray(np.rint(np.clip(rgb,0,1)*255).astype(np.uint8))
    x=np.asarray(image.resize((512,512),Image.Resampling.BILINEAR),np.float32)/255
    x=((x-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)).transpose(2,0,1)[None]
    logits=session.run(None,{session.get_inputs()[0].name:x})[0]
    if logits.ndim!=4 or logits.shape[:2]!=(1,18) or not np.isfinite(logits).all():
        raise ValueError('部位模型输出必须为有限[1,18,H,W] ATR logits，请检查模型文件。')
    maps=np.stack([np.asarray(Image.fromarray(c).resize(image.size,Image.Resampling.BILINEAR)) for c in logits[0]])
    p=np.exp(maps-maps.max(0,keepdims=True));return p/p.sum(0,keepdims=True)


def parse_parts(session,rgb,foreground,remove_headwear=True):
    p=probabilities(session,rgb);labels=p.argmax(0)
    body=np.isin(labels,BODY_IDS)&(foreground>.01)
    garment=np.isin(labels,GARMENT_IDS)&(foreground>.01)
    accessory=np.zeros(foreground.shape,bool)
    head_box=None
    if remove_headwear:
        hair=(labels==2)&(foreground>.2)
        cc,n=ndi.label(hair)
        if n:
            sizes=np.bincount(cc.ravel());sizes[0]=0;hair=cc==sizes.argmax()
            ys,xs=np.nonzero(hair)
            if len(xs)>=8:
                pad=max(2,round((xs.max()-xs.min())*.5))
                h,w=foreground.shape
                x0,y0=max(0,int(xs.min())-pad),max(0,int(ys.min())-pad//2)
                x1,y1=min(w,int(xs.max())+pad+1),min(h,int(ys.max())+pad//3+1)
                hp=probabilities(session,rgb[y0:y1,x0:x1])
                cut=(hp[[0,1,3,16,17]].sum(0)>.55)&(hp[list(BODY_IDS)].sum(0)<.35)
                # A tight head crop can mislabel the neck/back: global confident
                # face/skin and hair always guard against those false deletions.
                cut&=(p[11,y0:y1,x0:x1]<.5)&(p[2,y0:y1,x0:x1]<.95)
                accessory[y0:y1,x0:x1]=cut&(foreground[y0:y1,x0:x1]>.01)
                head_box=[x0,y0,x1,y1]
    return {'body':body.astype(np.float32),'garment':garment.astype(np.float32),
            'accessory':accessory.astype(np.float32),'labels':labels,
            'head_box':head_box,'source':'local ATR ONNX; full-frame plus head crop'}
