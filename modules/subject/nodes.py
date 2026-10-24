"""Enhanced subject node. All model and scientific imports are execution-time only."""


class PersonSubjectClean:
    CATEGORY='LL 节点库/图像工具/人物轮廓'
    FUNCTION='clean'
    RETURN_TYPES=('IMAGE','IMAGE','IMAGE','MASK','IMAGE','MASK','STRING')
    RETURN_NAMES=('clean_rgb','rgba','clean_depth','keep_mask','stage_preview','skin_removed_mask','report')
    DESCRIPTION='从原始RGB重新提取人物，结合局部深度细化边界；同MASK输出RGB和深度。肤色增强默认关闭。SAM2模式需本地模型与骨架或保留提示。'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{
            'image':('IMAGE',{'tooltip':'原始RGB图，不能先把误抠区域填黑；RGB输出保留此画布。'}),
            'segmentation':(['semantic_sam2','sam2','external_mask'],{'default':'semantic_sam2','tooltip':'推荐人物语义引导SAM2；sam2仅用骨架/保留提示；external_mask使用已有人物遮罩细化。'}),
            'model_name':(['sam2.1_hiera_tiny.pt','sam2.1_hiera_small.pt','sam2.1_hiera_base_plus.pt','sam2.1_hiera_large.pt'],{'default':'sam2.1_hiera_tiny.pt'}),
            'device':(['auto','cpu'],{'default':'auto'}),
            'mode':(['person','body_trim'],{'default':'person','tooltip':'完整人物提取，或继续修剪外扩服饰；缺少完整骨架时跳过外扩修剪并报告。'}),
            'person_index':('INT',{'default':0,'min':0,'max':99}),
            'confidence':('FLOAT',{'default':.3,'min':0.,'max':1.,'step':.05}),
            'analysis_size':('INT',{'default':512,'min':256,'max':1024,'step':64,'tooltip':'分析画布最长边；输出图像保持原尺寸。'}),
            'edge_strength':('FLOAT',{'default':.7,'min':0.,'max':1.,'step':.05}),
            'depth_weight':('FLOAT',{'default':.65,'min':0.,'max':1.,'step':.05,'tooltip':'联合边界中的深度权重；0只用RGB，非全局深度阈值。'}),
            'edge_band':('INT',{'default':16,'min':1,'max':64,'tooltip':'分析画布中重新判断的边缘带宽，像素。'}),
            'trim_scale':('FLOAT',{'default':1.,'min':.5,'max':1.8,'step':.05}),
            'skin_enabled':('BOOLEAN',{'default':False,'tooltip':'肤色辅助边缘净化；需要有效深度，样本不足时跳过。'}),
            'skin_strength':('FLOAT',{'default':.5,'min':0.,'max':1.,'step':.05}),
            'skin_band':('INT',{'default':10,'min':1,'max':48,'tooltip':'仅在肢体内侧边缘带检查；单位为分析像素。'}),
            'skin_protection':('FLOAT',{'default':.7,'min':0.,'max':1.,'step':.05}),
            'feather':('INT',{'default':1,'min':0,'max':8}),
            'rgb_background':(['black','white'],{'default':'black'}),
            'failure_policy':(['stop','keep_subject'],{'default':'stop','tooltip':'细化结果明显异常时停止，或保留初始分割并明确报告；模型缺失始终报错。'}),
        },'optional':{
            'depth_image':('IMAGE',{'tooltip':'原始深度；须同构图／裁切，可不同等比例分辨率。缺省只做RGB分割。'}),
            'keypoints':('POSE_KEYPOINT',{'tooltip':'SDPose／DWPose原始18/25关键点；SAM2自动提示使用。'}),
            'foreground_mask':('MASK',{'tooltip':'SAM2模式仅作软参考；external_mask模式作为初始人物遮罩。'}),
            'protect_mask':('MASK',{'tooltip':'强制保留，也为SAM2提供正提示。'}),
            'exclude_mask':('MASK',{'tooltip':'强制排除，也为SAM2提供负提示；最终优先于保留。'}),
            'skin_mask':('MASK',{'tooltip':'可选：来自人体解析的可靠裸露皮肤区域，限定肤色取样。不是人体完整轮廓。'}),
            'foot_protection':('BOOLEAN',{'default':True,'tooltip':'保护完整脚掌／鞋；仅保留初始分割已有区域，需要有效脚踝关键点。'}),
            'foot_scale':('FLOAT',{'default':1.2,'min':.5,'max':3.,'step':.05,'tooltip':'只调脚掌保护范围，不放大小腿；近镜头大脚或长鞋可逐步增加。'}),
            'hand_protection':('BOOLEAN',{'default':True,'tooltip':'独立保护手掌／手指；与脚掌、肤色开关互不依赖。'}),
            'hand_scale':('FLOAT',{'default':1.15,'min':.5,'max':3.,'step':.05,'tooltip':'只调手掌保护范围；保护过宽时缩小或接明确删除遮罩。'}),
        }}

    def clean(self,image,segmentation='semantic_sam2',model_name='sam2.1_hiera_tiny.pt',device='auto',mode='person',
              person_index=0,confidence=.3,analysis_size=512,edge_strength=.7,depth_weight=.65,edge_band=16,
              trim_scale=1.,skin_enabled=False,skin_strength=.5,skin_band=10,skin_protection=.7,feather=1,
              rgb_background='black',failure_policy='stop',depth_image=None,keypoints=None,
              foreground_mask=None,protect_mask=None,exclude_mask=None,skin_mask=None,
              foot_protection=True,foot_scale=1.2,hand_protection=True,hand_scale=1.15):
        import json
        import math
        import warnings
        import numpy as np
        import torch
        from scipy import ndimage as ndi
        from ..contour.processing import _mask_input
        from ..contour.geometry import parse_frames
        from .prompts import pose_guides,sparse_points,spread_points
        from .processing import resize,clean_frame
        from .model import load_predictor,predict,load_semantic,semantic_probability,MODELS

        def validate_image(value,label):
            if not isinstance(value,torch.Tensor) or value.ndim!=4 or value.shape[-1] not in (3,4) or min(value.shape)==0:
                raise ValueError(label+'必须为非空[B,H,W,3或4] IMAGE。')
            if not value.is_floating_point() or not torch.isfinite(value).all() or value.min()<0 or value.max()>1:
                raise ValueError(label+'必须是0～1有限浮点IMAGE。')
        validate_image(image,'原图')
        for name,value,lo,hi in [('confidence',confidence,0,1),('edge_strength',edge_strength,0,1),('depth_weight',depth_weight,0,1),
              ('trim_scale',trim_scale,.5,1.8),('skin_strength',skin_strength,0,1),('skin_protection',skin_protection,0,1),
              ('foot_scale',foot_scale,.5,3),('hand_scale',hand_scale,.5,3)]:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
                raise ValueError(f'{name}范围为{lo}～{hi}。')
        for name,value,lo,hi in [('analysis_size',analysis_size,256,1024),('person_index',person_index,0,99),('edge_band',edge_band,1,64),('skin_band',skin_band,1,48),('feather',feather,0,8)]:
            if type(value)is not int or not lo<=value<=hi:raise ValueError(name+'整数范围无效。')
        if type(skin_enabled)is not bool:raise ValueError('skin_enabled必须为布尔值。')
        if type(foot_protection)is not bool or type(hand_protection)is not bool:raise ValueError('手掌／脚掌保护必须为布尔值。')
        if segmentation not in ('semantic_sam2','sam2','external_mask') or mode not in ('person','body_trim') or device not in ('auto','cpu') or rgb_background not in ('black','white') or failure_policy not in ('stop','keep_subject') or model_name not in MODELS:
            raise ValueError('增强提取选项无效。')
        b,h,w,_=image.shape
        if h*w>64_000_000:raise ValueError('单帧图像超过6400万像素。')
        arrays={}
        for name,value in [('foreground',foreground_mask),('protect',protect_mask),('exclude',exclude_mask),('skin_hint',skin_mask)]:
            if value is not None:
                if not isinstance(value,torch.Tensor):raise ValueError(name+'须为MASK。')
                arrays[name]=_mask_input(value.detach().float().cpu().numpy(),b,h,w,name)
        if segmentation=='external_mask' and 'foreground' not in arrays:
            raise ValueError('external_mask模式需要连接foreground_mask。')
        frames=parse_frames(keypoints) if keypoints is not None else None
        if frames is not None and len(frames) not in (1,b):raise ValueError('骨架帧数必须为1或与图像数量相同。')
        depths=None
        if depth_image is not None:
            validate_image(depth_image,'深度图')
            if len(depth_image) not in (1,b):raise ValueError('深度帧数必须为1或与图像数量相同。')
            if abs((depth_image.shape[2]/depth_image.shape[1])/(w/h)-1)>.02:raise ValueError('深度与RGB宽高比不一致，请先对齐裁切。')
            depths=depth_image.detach().float().cpu().numpy()
        size=(max(1,round(w*min(1,analysis_size/max(h,w)))),max(1,round(h*min(1,analysis_size/max(h,w)))))
        predictor=None;semantic_model=None;results=[];stage_results=[];skin_results=[];reports=[]
        try:
            for i in range(b):
                src=image[i].detach().float().cpu().numpy()
                rgb=resize(src[...,:3],size)
                masks={k:resize(v[0 if len(v)==1 else i],size) for k,v in arrays.items()}
                parsed=None;reason='未提供骨架';box=None;geometry=np.zeros(rgb.shape[:2],np.float32)
                positive=np.empty((0,2),np.float32)
                if frames is not None:
                    parsed,positive,box,geometry,reason=pose_guides(frames[0 if len(frames)==1 else i],person_index,*size,confidence,
                        include_feet=foot_protection,include_hands=hand_protection)
                if 'protect' in masks:positive=np.concatenate([positive,sparse_points(masks['protect'])])
                negative=sparse_points(masks['exclude']) if 'exclude' in masks else np.empty((0,2),np.float32)
                if segmentation in ('semantic_sam2','sam2'):
                    active_device='cuda' if device=='auto' and torch.cuda.is_available() else 'cpu'
                    probability=None
                    if segmentation=='semantic_sam2':
                        if semantic_model is None:semantic_model=load_semantic(active_device)
                        probability=semantic_probability(semantic_model,rgb)
                        semantic_points=spread_points(probability>.8,12)
                        if not len(semantic_points):semantic_points=spread_points(probability>.5,12)
                        if not len(positive):
                            if person_index!=0:raise ValueError('选择其他人物需连接骨架关键点。')
                            positive=semantic_points;reason='未提供骨架：提取语义人物，可能包含多人；外扩修剪需要骨架'
                    if not len(positive):raise ValueError('SAM2需要骨架关键点或protect_mask作为人物正提示。')
                    if predictor is None:predictor=load_predictor(model_name,active_device)
                    # Distant false foreground can provide negative hints; it is not intersected with output.
                    # Geometry alone cannot label background under strong foreshortening.
                    # Only explicit exclusions are negative prompts; the old foreground stays soft.
                    initial=predict(predictor,rgb,positive,negative,box,masks.get('foreground'),semantic=probability)
                else:
                    initial=masks['foreground']
                    positive=np.concatenate([positive,sparse_points(initial,16)])
                if not np.any(initial>.5):raise ValueError('初始人物遮罩为空。')
                depth=None if depths is None else resize(depths[0 if len(depths)==1 else i,:,:,:3],size)
                keep,stages,detail=clean_frame(rgb,initial,parsed,positive,negative,depth=depth,
                    protect=masks.get('protect'),exclude=masks.get('exclude'),skin_hint=masks.get('skin_hint'),
                    mode=mode,edge_strength=edge_strength,depth_weight=depth_weight,edge_band=edge_band,trim_scale=trim_scale,
                    skin_enabled=skin_enabled,skin_strength=skin_strength,skin_band=skin_band,skin_protection=skin_protection,feather=feather,
                    foot_protection=foot_protection,foot_scale=foot_scale,hand_protection=hand_protection,hand_scale=hand_scale)
                baseline=(initial>.5)&~(masks['exclude']>.5) if 'exclude' in masks else initial>.5
                coverage=float((keep>.5).sum()/max(1,baseline.sum()))
                if coverage<.3:
                    if failure_policy=='stop':raise RuntimeError(f'第{i+1}帧保留面积不足初始人物的30%，已停止；检查骨架、裁切和修剪设置。')
                    keep=initial.copy()
                    if 'protect' in masks:keep=np.maximum(keep,masks['protect'])
                    if 'exclude' in masks:keep*=1-masks['exclude']
                    stages[-1]=keep;detail['fallback']='细化结果异常，明确保留初始人物';warnings.warn(detail['fallback'],RuntimeWarning)
                removed=detail.pop('skin_removed_mask')
                if 'fallback' in detail:removed=np.zeros_like(removed)
                alpha=src[...,3] if src.shape[-1]==4 else np.ones((h,w),np.float32)
                results.append(resize(keep,(w,h))*alpha)
                skin_results.append(resize(removed,(w,h)))
                panels=[]
                for stage in stages:
                    color=np.stack([1-stage,stage,np.zeros_like(stage)],-1)
                    panels.append(np.clip(rgb*.6+color*.4,0,1))
                stage_results.append(resize(np.concatenate(panels,axis=1),(w*3,h)))
                detail.update(frame=i+1,backend=segmentation,pose_note=reason or '完整骨架',retained_fraction=round(coverage,4))
                reports.append(detail)
        finally:
            if predictor is not None:
                predictor.reset_predictor();predictor.model.to('cpu')
                del predictor
            if semantic_model is not None:
                semantic_model.to('cpu');del semantic_model
        keep=torch.from_numpy(np.stack(results)).to(image.device)
        rgb=image[...,:3].float();bg=0. if rgb_background=='black' else 1.
        clean_rgb=rgb*keep[...,None]+bg*(1-keep[...,None])
        rgba=torch.cat([rgb,keep[...,None]],-1)
        if depth_image is None:
            clean_depth=torch.zeros_like(clean_rgb)
        else:
            from torch.nn import functional as F
            dh,dw=depth_image.shape[1:3]
            dm=F.interpolate(keep[:,None],size=(dh,dw),mode='bilinear',align_corners=False)[:,0].to(depth_image.device)
            source=depth_image.expand(b,-1,-1,-1) if len(depth_image)==1 else depth_image
            clean_depth=source.float().clone();clean_depth[...,:3]*=dm[...,None]
            if source.shape[-1]==4:clean_depth[...,3]*=dm
            clean_depth=clean_depth.to(image.device)
        report=json.dumps({'depth_provided':depths is not None,'depth_output':'原深度乘最终遮罩，保持深度原画布' if depths is not None else '未输入深度：clean_depth是全黑占位，不能作为深度条件',
            'stage_order':['初始主体','RGB/深度提炼','最终修剪'],'frames':reports},ensure_ascii=False,indent=2)
        return clean_rgb,rgba,clean_depth,keep,torch.from_numpy(np.stack(stage_results)).to(image.device),torch.from_numpy(np.stack(skin_results)).to(image.device),report
