"""Marker watershed on joint RGB/depth edges, and conservative skin edge cleanup.

Uses SciPy's mature watershed_ift and morphology. Depth is relative per-frame,
never interpreted as a metric distance or thresholded globally by foreground color.
"""
import numpy as np
from scipy import ndimage as ndi


def unit_depth(depth):
    d=np.asarray(depth,np.float32)
    if d.ndim==3:d=d[...,:3].mean(-1)
    lo,hi=np.quantile(d,[.01,.99])
    if hi-lo<1e-5:return None
    return np.clip((d-lo)/(hi-lo),0,1)


def edge_strength(data):
    if data.ndim==2:data=data[...,None]
    smooth=ndi.gaussian_filter(data,sigma=(.8,.8,0))
    dy=ndi.sobel(smooth,axis=0)/8;dx=ndi.sobel(smooth,axis=1)/8
    magnitude=np.sqrt((dy*dy+dx*dx).sum(-1))
    scale=max(float(np.quantile(magnitude,.95)),.01)
    return np.clip(magnitude/scale,0,1)


def seed_mask(points,shape,radius=2):
    seeds=np.zeros(shape,bool)
    for x,y in points:
        if 0<=x<shape[1] and 0<=y<shape[0]:seeds[int(y),int(x)]=True
    return ndi.binary_dilation(seeds,iterations=radius) if radius else seeds


def refine_subject(rgb,initial,positive,negative,depth=None,strength=.7,depth_weight=.65,band=12,protect=None,exclude=None):
    base=initial>.5
    if strength==0:return initial.copy(),{'depth_active':False,'refinement':'disabled'}
    inside=ndi.distance_transform_edt(base)
    outside=ndi.distance_transform_edt(~base)
    radius=max(2,int(band))
    # Certain interior is retained; only the requested boundary band is reconsidered.
    fg=inside>radius
    fg|=seed_mask(positive,base.shape)&base
    bg=outside>radius
    bg|=seed_mask(negative,base.shape)
    if protect is not None:fg|=protect>.5
    if exclude is not None:bg|=exclude>.5
    fg&=~bg
    if not fg.any() or not bg.any():return initial.copy(),{'depth_active':False,'refinement':'insufficient seeds'}
    d=None if depth is None else unit_depth(depth)
    elevation=edge_strength(rgb)
    if d is not None and depth_weight>0:
        # Local core depth reference: follows different limbs, not one body-wide range.
        _,indices=ndi.distance_transform_edt(~fg,return_indices=True)
        expected=d[tuple(indices)]
        discrepancy=np.abs(d-expected)
        tolerance=.04+.012*np.minimum(ndi.distance_transform_edt(~fg),radius)
        depth_evidence=np.maximum(edge_strength(d),np.clip((discrepancy-tolerance)/.2,0,1))
        elevation=(1-depth_weight)*elevation+depth_weight*depth_evidence
    # Soft prior breaks flat-region ties while retaining the possibility of edge correction.
    elevation=np.clip(elevation*.9+.1*np.minimum(np.abs(inside-outside)/radius,1),0,1)
    markers=np.zeros(base.shape,np.int32);markers[fg]=1;markers[bg]=2
    labels=ndi.watershed_ift(np.rint(elevation*65535).astype(np.uint16),markers)
    candidate=(labels==1)&(outside<=radius)
    if d is None or depth_weight==0:candidate&=base
    # Strength changes the uncertain band, keeping exact output when disabled.
    allowed=max(1,int(round(radius*strength)))
    changed=np.logical_xor(candidate,base)&(np.minimum(np.maximum(inside,0),radius)<=allowed)&(outside<=allowed)
    result=base.copy();result[changed]=candidate[changed]
    return result.astype(np.float32),{'depth_active':d is not None and depth_weight>0,'refinement':'RGB+depth watershed' if d is not None and depth_weight>0 else 'RGB watershed'}


def chroma(rgb):
    # Chroma only: brightness variation is largely left to the depth/edge evidence.
    r,g,b=np.moveaxis(rgb,-1,0)
    return np.stack([-.168736*r-.331264*g+.5*b,.5*r-.418688*g-.081312*b],-1)


def skin_cleanup(rgb,mask,limb_regions,depth=None,skin_hint=None,strength=.5,band=8,protection=.7):
    """Never erase unexposed garment regions merely because they are not skin color."""
    if strength==0:return mask.copy(),{'skin':'zero strength','removed':0,'sampled_parts':0}
    d=None if depth is None else unit_depth(depth)
    if d is None:return mask.copy(),{'skin':'跳过：缺少有效深度，不能交叉验证肤色边缘','removed':0,'sampled_parts':0}
    base=mask>.5;distance=ndi.distance_transform_edt(base);colors=chroma(rgb)
    result=mask.copy();sampled=0
    for region,core in limb_regions:
        core=core&base&(distance>max(1,band*protection*.25))
        if skin_hint is not None:core&=skin_hint>.5
        else:
            # Conservative exposed-skin proposal, not semantic proof of skin.
            r,g,b=np.moveaxis(rgb,-1,0)
            plausible=(r>g*.98)&(r>b*1.08)&(g>b*.8)&(r>.04)&((r-b)>.015)
            if core.sum()<20 or np.count_nonzero(core&plausible)<core.sum()*.8:continue
            core&=plausible
        if core.sum()<20:continue
        samples=colors[core];mean=np.median(samples,axis=0)
        spread=np.maximum(np.median(np.abs(samples-mean),axis=0)*1.4826,.012)
        if np.max(spread)>.065:continue
        sampled+=1
        mismatch=np.sqrt(np.square((colors-mean)/spread).sum(-1))
        _,indices=ndi.distance_transform_edt(~core,return_indices=True)
        expected=d[tuple(indices)]
        zspread=max(float(np.median(np.abs(d[core]-np.median(d[core]))))*1.4826,.025)
        # Depth must disagree too; a skin shadow alone cannot trigger deletion.
        bad_depth=np.abs(d-expected)>(.05+zspread*(1+protection))
        threshold=6-2*strength+2*protection
        edge=base&(distance<=band*strength)&region
        remove=edge&(mismatch>threshold)&bad_depth&~core
        result[remove]=0
    count=int(np.count_nonzero((mask>.5)&(result<=.5)))
    return result,{'skin':'已执行（自动肤色取样是启发式）' if sampled else '跳过：没有可靠裸露肢体样本','removed':count,'sampled_parts':sampled}
