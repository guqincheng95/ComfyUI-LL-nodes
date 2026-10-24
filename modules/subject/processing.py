import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from .prompts import LIMBS
from .refinement import refine_subject, skin_cleanup
from ..contour.geometry import render_person, observed_width
from ..contour.extremities import extremity_regions, extremity_support, extremity_summary


def resize(array,size,nearest=False):
    """Resize analysis only; result images always retain their native canvases."""
    mode=Image.Resampling.NEAREST if nearest else Image.Resampling.BILINEAR
    if array.ndim==2:return np.asarray(Image.fromarray(array.astype(np.float32)).resize(size,mode))
    return np.stack([resize(array[...,i],size,nearest) for i in range(array.shape[-1])],-1)


def limb_regions(parsed,shape,subject):
    if parsed is None:return []
    p=parsed['body'];h,w=shape;regions=[]
    good=np.isfinite(p).all(1)
    length=np.linalg.norm(p[[8,11],:2].mean(0)-p[[2,5],:2].mean(0)) if all(good[i] for i in (2,5,8,11)) else max(h,w)*.22
    for a,b in LIMBS:
        if not good[a] or not good[b]:continue
        delta=p[b,:2]-p[a,:2];normal=np.array([-delta[1],delta[0]])/max(np.linalg.norm(delta),1)
        base=max(3,length*(.1 if a<8 else .14))
        centers=[p[a,:2]*(1-t)+p[b,:2]*t for t in (.3,.5,.7)]
        radius=observed_width(subject,centers,normal,base,max_scale=3)
        masks=[]
        for r in (radius*1.15,max(1,radius*.18)):
            im=Image.new('L',(w,h));draw=ImageDraw.Draw(im)
            draw.line([tuple(p[a,:2]),tuple(p[b,:2])],fill=255,width=max(1,round(r*2)))
            masks.append(np.asarray(im)>0)
        regions.append(tuple(masks))
    return regions


def clean_frame(rgb,initial,parsed,positive,negative,*,depth=None,protect=None,exclude=None,skin_hint=None,
                mode='person',edge_strength=.7,depth_weight=.65,edge_band=12,trim_scale=1.,
                skin_enabled=False,skin_strength=.5,skin_band=8,skin_protection=.7,feather=1,
                foot_protection=True,foot_scale=1.2,hand_protection=True,hand_scale=1.15):
    initial=np.clip(initial,0,1)
    parts=extremity_regions(parsed,rgb.shape[1],rgb.shape[0],foreground=initial,
        foot_protection=foot_protection,foot_scale=foot_scale,hand_protection=hand_protection,hand_scale=hand_scale)
    automatic=extremity_support(parts,initial.shape)
    effective_protect=automatic if protect is None else np.maximum(automatic,protect)
    refined,detail=refine_subject(rgb,initial,positive,negative,depth,edge_strength,depth_weight,edge_band,effective_protect,exclude)
    # Keep observed hands/feet from being lost at any later stage. Explicit
    # exclusion still has final priority; no missing foreground is fabricated.
    refined=np.maximum(refined,automatic)
    if exclude is not None:refined*=1-exclude
    trimmed=refined.copy();trim_reason='完整人物模式'
    if mode=='body_trim':
        geometry,reason=render_person(parsed,rgb.shape[1],rgb.shape[0],foreground=refined,
             head_scale=trim_scale,torso_scale=trim_scale,arm_scale=trim_scale,leg_scale=trim_scale,
             observed_max_scale=2.5) if parsed is not None else (None,'无有效骨架')
        if geometry is not None:
            trimmed=np.minimum(trimmed,geometry);trim_reason='已修剪外扩，局部宽度从主体观测'
        else:trim_reason='跳过外扩修剪，保留已分割人物：'+reason
    before_skin=trimmed.copy()
    skin_info={'skin':'关闭','removed':0,'sampled_parts':0}
    if skin_enabled:
        trimmed,skin_info=skin_cleanup(rgb,trimmed,limb_regions(parsed,rgb.shape[:2],refined),depth,skin_hint,
                                     skin_strength,skin_band,skin_protection)
    removed_by_skin=(before_skin>.5)&(trimmed<.5)
    trimmed=np.maximum(trimmed,effective_protect)
    if exclude is not None:trimmed*=1-exclude
    # Preserve every component associated with a valid body seed; not just the largest component.
    labels,_=ndi.label(trimmed>.5)
    ids=np.unique(labels[positive[:,1].astype(int),positive[:,0].astype(int)]) if len(positive) else np.unique(labels)
    ids=np.union1d(ids,np.unique(labels[effective_protect>.5]))
    if len(ids[ids>0]):trimmed*=np.isin(labels,ids[ids>0])
    if feather:
        smooth=ndi.gaussian_filter(trimmed,float(feather))
        trimmed=np.minimum(trimmed,smooth)
    if exclude is not None:trimmed*=1-exclude
    trimmed=np.maximum(trimmed,effective_protect*(1-exclude if exclude is not None else 1))
    stages=np.stack([initial,refined,trimmed],axis=0)
    detail.update(skin_info);detail['trim']=trim_reason
    detail['extremities']={'feet_enabled':foot_protection,'foot_scale':foot_scale,
        'hands_enabled':hand_protection,'hand_scale':hand_scale,'parts':extremity_summary(parts),
        'note':'保护初始分割已存在的手脚；未提供有效骨架时跳过，初始漏分区域需保留提示或修正分割'}
    detail['skin_removed_mask']=(removed_by_skin&(trimmed<.5)).astype(np.float32)
    detail['removed']=int(detail['skin_removed_mask'].sum())
    return np.clip(trimmed,0,1),stages,detail
