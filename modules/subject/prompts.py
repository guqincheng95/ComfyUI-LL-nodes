"""Pose-guided prompts, not a new pose estimator or anatomical reconstruction."""
import numpy as np
from scipy import ndimage as ndi
from ..contour.geometry import parse_person, render_person

LIMBS = ((2,3),(3,4),(5,6),(6,7),(8,9),(9,10),(11,12),(12,13))


def pose_guides(frame, index, width, height, confidence=.3):
    cw,ch,people=frame
    if not 0 <= index < len(people):
        raise ValueError('没有检测到指定人物，请检查关键点或提供人物保留提示。')
    parsed=parse_person(people[index],(cw,ch),(width,height),confidence)
    body=parsed['body']
    if len(body)!=18:
        raise ValueError('增强提取需要OpenPose 18/25格式关键点。')
    good=np.isfinite(body).all(1)
    points=[]
    for i in (0,2,3,4,5,6,7,8,9,10,11,12,13):
        if good[i]:points.append(body[i,:2])
    for a,b in LIMBS:
        if good[a] and good[b]:points.append((body[a,:2]+body[b,:2])*.5)
    if all(good[i] for i in (2,5,8,11)):
        points.extend([body[[2,5,8,11],:2].mean(0),body[[8,11],:2].mean(0)])
    points=np.asarray(points,dtype=np.float32).reshape(-1,2)
    points=points[(points[:,0]>=0)&(points[:,0]<width)&(points[:,1]>=0)&(points[:,1]<height)]
    if len(points)<3:raise ValueError('有效人物提示不足3点，无法可靠定位人物。')
    geometry,reason=render_person(parsed,width,height)
    if geometry is None:geometry=np.zeros((height,width),np.float32)
    # A broad envelope supplies negative hints, never a hard segmentation boundary.
    # Pose extrema are not object extrema (large near-camera feet/hair can extend far).
    # Do not constrain SAM with a tight pose bounding box.
    return parsed,points,None,geometry,reason.replace('，保留原帧','')


def sparse_points(mask, count=8):
    """Interior points from explicit masks, sampled deterministically across components."""
    labels,n=ndi.label(mask>.5)
    points=[]
    for i in sorted(range(1,n+1),key=lambda i:np.count_nonzero(labels==i),reverse=True)[:count]:
        distance=ndi.distance_transform_edt(labels==i)
        y,x=np.unravel_index(np.argmax(distance),distance.shape);points.append([x,y])
    return np.asarray(points,np.float32).reshape(-1,2)


def spread_points(mask,count=12):
    """Cover separated parts of one semantic person, not just the thick torso center."""
    distance=ndi.distance_transform_edt(mask)
    ys,xs=np.nonzero(distance>max(1,min(mask.shape)*.004))
    if not len(xs):return sparse_points(mask,count)
    stride=max(1,len(xs)//4000)
    candidates=np.stack([xs[::stride],ys[::stride]],-1).astype(np.float32)
    center=np.array(np.unravel_index(np.argmax(distance),distance.shape))[::-1].astype(np.float32)
    selected=[center];nearest=np.square(candidates-center).sum(-1)
    for _ in range(count-1):
        i=int(np.argmax(nearest))
        if nearest[i]<16:break
        selected.append(candidates[i]);nearest=np.minimum(nearest,np.square(candidates-candidates[i]).sum(-1))
    return np.asarray(selected,np.float32)


def select_candidate(masks,scores,points,negative,hint=None):
    """Prefer masks covering pose seeds, penalize prompt violations and excess area."""
    values=[]
    for mask,score in zip(masks,scores):
        y=points[:,1].astype(int);x=points[:,0].astype(int)
        coverage=mask[y,x].mean() if len(points) else 0
        wrong=mask[negative[:,1].astype(int),negative[:,0].astype(int)].mean() if len(negative) else 0
        overlap=0
        if hint is not None and np.any(hint>.5):
            overlap=np.logical_and(mask,hint>.5).sum()/max(1,np.logical_or(mask,hint>.5).sum())
        values.append(3*coverage-2*wrong+.3*float(score)+.15*overlap-.15*mask.mean())
    if not values:raise ValueError('分割模型没有返回候选遮罩。')
    selected=np.asarray(masks[int(np.argmax(values))],np.float32)
    if selected.sum()<4:raise ValueError('分割结果为空，请检查骨架／保留提示。')
    return selected
