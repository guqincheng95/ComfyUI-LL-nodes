"""Delete unwanted material while keeping the incoming foreground matte intact."""
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull,QhullError


def torso_bridge(labels,body,parsed,padding):
    """Preserve the visible clothed torso between observed anchors, not a body render."""
    h,w=body.shape;points=[]
    if parsed is not None and len(parsed.get('body',[]))==18:
        p=parsed['body'];indices=(2,5,8,11)
        if np.isfinite(p[list(indices)]).all():points=p[list(indices),:2].tolist()
    if not points and labels is not None:
        legs=np.isin(labels,[12,13]);hair=labels==2
        ly,lx=np.nonzero(legs);hy,hx=np.nonzero(hair)
        if len(ly)>=20 and len(hy)>=8:
            yy=np.indices(body.shape)[0]
            upper=(labels==11)&(yy>hy.max())
            leg_top=legs&(yy<ly.min()+(ly.max()-ly.min())*.2)
            ys,xs=np.nonzero(upper|leg_top)
            if upper.sum()>=8 and leg_top.sum()>=8:
                stride=max(1,len(xs)//1500);points=np.stack([xs[::stride],ys[::stride]],-1)
    bridge=np.zeros(body.shape,bool)
    if len(points)>=3:
        points=np.asarray(points)
        try:
            hull=points[ConvexHull(points).vertices]
            image=Image.new('L',(w,h));ImageDraw.Draw(image).polygon([tuple(x) for x in hull],fill=255)
            bridge=ndi.distance_transform_edt(~(np.asarray(image)>0))<=padding
        except QhullError:
            pass
    return bridge


def semantic_cuts(initial,parts,*,parsed=None,mode='body_trim',garment_margin=.15,trim_scale=1.,remove_headwear=True):
    body=(parts['body']>.5)&(initial>.01)
    garment=(parts['garment']>.5)&(initial>.01)
    accessory=(parts['accessory']>.5)&(initial>.01) if remove_headwear else np.zeros(initial.shape,bool)
    cut=accessory.copy();ys,xs=np.nonzero(body)
    note='完整人物模式：不修剪外扩衣料'
    garment_cut=np.zeros_like(cut)
    if mode=='body_trim':
        # A small head/arm-only mask cannot establish a whole-body clothing cut.
        has_legs=bool(np.isin(parts.get('labels',np.empty(0)),[12,13]).sum()>=20) if parts.get('labels') is not None else (len(ys)>20 and np.ptp(ys)>np.ptp(np.nonzero(initial>.5)[0])*.55)
        if len(xs)>=20 and has_legs and garment.any():
            span=max(8,float(xs.max()-xs.min()))
            core=ndi.binary_fill_holes(body)
            bridge=torso_bridge(parts.get('labels'),body,parsed,span*.1*trim_scale)
            margin=span*garment_margin*trim_scale
            # Coarse semantic labels miss subpixel fabric edges. Expand only
            # the candidate clothing zone, still clipped to the incoming matte
            # and away from observed body parts; do not leave a detached outline.
            garment_zone=ndi.distance_transform_edt(~garment)<=max(2,span*.04)
            garment_cut=garment_zone&(initial>.01)&~bridge&(ndi.distance_transform_edt(~core)>margin)
            cut|=garment_cut;note='按可见部位与躯干连接范围删除外扩衣料，不补画身体'
        else:
            note='跳过衣料剪枝：没有可剪衣料' if not garment.any() else '跳过衣料剪枝：缺少可靠可见下肢／身体部位，不从头部样本推断整身'
    # Reject tiny disconnected leftover cloth, while retaining every observed
    # body component, including small hands rather than only the largest person.
    remaining=(initial>.01)&~cut
    cc,_=ndi.label(remaining)
    ids=np.unique(cc[body]);ids=ids[ids>0]
    if mode=='body_trim' and len(ids):cut|=garment&remaining&~np.isin(cc,ids)
    cut&=~body
    # A confident accessory removal is a separate semantic decision from the
    # broad pose head envelope; it must not be restored by that envelope.
    cut|=accessory
    radius=max(1,round(max(initial.shape)/512))
    protected=ndi.binary_dilation(body,iterations=radius)&(initial>.01)&~cut
    return cut.astype(np.float32),np.minimum(initial,protected),{
        'source':parts.get('source','external masks'),'garment':note,
        'garment_removed_pixels':int(garment_cut.sum()),'headwear_removed_pixels':int(accessory.sum()),
        'head_box':parts.get('head_box'),'body_pixels':int(body.sum())}


def feather_new_cuts(initial,keep,sigma):
    """Feather only newly cut edges: an untouched incoming matte is an identity."""
    if not sigma:return keep
    gate=np.divide(keep,initial,out=np.ones_like(keep),where=initial>1e-6)
    gate=np.clip(gate,0,1)
    gate=np.minimum(gate,ndi.gaussian_filter(gate,float(sigma)))
    return initial*gate
