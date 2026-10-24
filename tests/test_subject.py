import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('subject_test_pkg',ROOT/'__init__.py')
pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from subject_test_pkg.modules.subject.refinement import refine_subject,skin_cleanup,unit_depth
from subject_test_pkg.modules.subject.prompts import pose_guides,select_candidate,spread_points
from subject_test_pkg.modules.subject.model import load_predictor


class SubjectTests(unittest.TestCase):
    def setUp(self):
        self.node=pkg.NODE_CLASS_MAPPINGS['LLPersonSubjectClean']()
        self.rgb=torch.ones((1,128,128,3),dtype=torch.float32)*.5
        self.mask=torch.zeros((1,128,128));self.mask[:,15:115,30:95]=1
        self.depth=torch.ones_like(self.rgb)*.2;self.depth[:,15:115,30:70]=.8
        self.pos=np.array([[50,35],[50,95]],np.float32);self.neg=np.array([[110,60]],np.float32)

    def test_depth_actually_changes_boundary_without_cutting_limb(self):
        rgb=self.rgb[0].numpy();initial=self.mask[0].numpy();depth=self.depth[0].numpy()
        a,_=refine_subject(rgb,initial,self.pos,self.neg,depth,1,0,32)
        b,report=refine_subject(rgb,initial,self.pos,self.neg,depth,1,1,32)
        self.assertGreater(a[20:110,75:90].mean(),.9)
        self.assertLess(b[20:110,75:90].mean(),.1)
        self.assertGreater(b[20:110,35:65].mean(),.95)
        self.assertTrue(report['depth_active'])

    def test_zero_strength_exact_and_flat_depth_skips(self):
        a,report=refine_subject(self.rgb[0].numpy(),self.mask[0].numpy(),self.pos,self.neg,self.depth[0].numpy(),0)
        np.testing.assert_array_equal(a,self.mask[0].numpy())
        self.assertIsNone(unit_depth(np.ones((32,32))))

    def test_rgb_rgba_depth_share_mask_and_preserve_source(self):
        original=self.rgb.clone();alpha=torch.ones_like(self.rgb[...,:1])*.6
        image=torch.cat([self.rgb,alpha],-1).half()
        out=self.node.clean(image,segmentation='external_mask',foreground_mask=self.mask,depth_image=self.depth,edge_strength=0,feather=0)
        rgb,rgba,depth,mask,preview,removed,report=out
        torch.testing.assert_close(mask,self.mask*image[...,3].float())
        torch.testing.assert_close(rgb,image[...,:3].float()*mask[...,None])
        torch.testing.assert_close(depth,self.depth*mask[...,None])
        torch.testing.assert_close(rgba[...,3],mask)
        self.assertEqual(preview.shape,(1,128,384,3));self.assertEqual(removed.sum(),0)
        self.assertTrue(torch.equal(self.rgb,original));self.assertEqual(rgba.dtype,torch.float32)
        self.assertTrue(json.loads(report)['depth_provided'])

    def test_native_depth_canvas_and_broadcast(self):
        image=self.rgb.repeat(2,1,1,1)
        depth=torch.ones((1,64,64,3))*.4
        out=self.node.clean(image,segmentation='external_mask',foreground_mask=self.mask,depth_image=depth,edge_strength=0,feather=0)
        self.assertEqual(out[2].shape,(2,64,64,3));torch.testing.assert_close(out[3][0],out[3][1])

    def test_no_depth_is_explicit_rgb_only(self):
        out=self.node.clean(self.rgb,segmentation='external_mask',foreground_mask=self.mask,edge_strength=0,skin_enabled=True,feather=0)
        self.assertEqual(out[2].sum(),0)
        self.assertIn('全黑占位',out[-1]);self.assertIn('缺少有效深度',out[-1])

    def test_protection_and_exclusion_priority(self):
        protect=torch.zeros_like(self.mask);protect[:,5:10,5:10]=1
        exclude=torch.zeros_like(self.mask);exclude[:,6:8,6:8]=1
        out=self.node.clean(self.rgb,segmentation='external_mask',foreground_mask=self.mask,protect_mask=protect,exclude_mask=exclude,edge_strength=0,feather=0)
        self.assertEqual(out[3][0,5,5],1);self.assertEqual(out[3][0,6,6],0)

    def test_bad_options_masks_and_frame_counts(self):
        for opts in [dict(edge_strength=-1),dict(depth_weight=float('nan')),dict(skin_enabled=1),dict(analysis_size=True),dict(segmentation='bad')]:
            with self.assertRaises(ValueError):self.node.clean(self.rgb,segmentation='external_mask' if 'segmentation' not in opts else opts.pop('segmentation'),foreground_mask=self.mask,**opts)
        for mask in [torch.ones(1,20,30),torch.ones(3,128,128),torch.full((1,128,128),float('nan'))]:
            with self.assertRaises(ValueError):self.node.clean(self.rgb,segmentation='external_mask',foreground_mask=mask)
        with self.assertRaises(ValueError):self.node.clean(self.rgb,segmentation='external_mask')
        with self.assertRaises(ValueError):self.node.clean(self.rgb,segmentation='external_mask',foreground_mask=self.mask,depth_image=torch.ones(1,20,30,3))
        with self.assertRaises(ValueError):self.node.clean(self.rgb,segmentation='sam2')

    def test_partial_pose_does_not_crop_near_camera_extrema(self):
        points=np.zeros((18,3));points[0]=[70,30,1];points[5]=[80,50,1];points[6]=[85,70,1];points[7]=[90,90,1]
        frame=(128,128,[{'pose_keypoints_2d':points.flatten().tolist()}])
        parsed,positive,box,geometry,reason=pose_guides(frame,0,128,128)
        self.assertIsNone(box);self.assertGreaterEqual(len(positive),3)
        self.assertFalse(geometry.any());self.assertNotIn('保留原帧',reason)

    def test_semantic_prompts_cover_head_and_body_not_just_torso(self):
        mask=np.zeros((160,100),bool);mask[10:35,40:60]=1;mask[30:145,25:75]=1
        points=spread_points(mask)
        self.assertLess(points[:,1].min(),25);self.assertGreater(points[:,1].max(),130)
        self.assertTrue(mask[points[:,1].astype(int),points[:,0].astype(int)].all())

    def test_default_semantic_mode_works_without_pose(self):
        class Dummy:
            model=None
            def __init__(self):self.model=self
            def reset_predictor(self):pass
            def to(self,*a):return self
        with patch('subject_test_pkg.modules.subject.model.load_semantic',return_value=Dummy()),patch('subject_test_pkg.modules.subject.model.semantic_probability',return_value=self.mask[0].numpy()),patch('subject_test_pkg.modules.subject.model.load_predictor',return_value=Dummy()),patch('subject_test_pkg.modules.subject.model.predict',return_value=self.mask[0].numpy()) as predict:
            out=self.node.clean(self.rgb,edge_strength=0,feather=0)
        self.assertGreater(len(predict.call_args.args[2]),3)
        self.assertIn('未提供骨架',out[-1]);self.assertFalse(self.node.INPUT_TYPES()['required']['skin_enabled'][1]['default'])

    def test_body_trim_removes_obvious_protrusion(self):
        from test_contour import fixture
        frame,fg,depth=fixture()
        image=torch.ones((1,400,240,3))*.5
        out=self.node.clean(image,segmentation='external_mask',foreground_mask=torch.from_numpy(fg)[None],keypoints=frame,mode='body_trim',edge_strength=0,feather=0)
        self.assertEqual(out[3][0,40,174],0)
        self.assertEqual(out[3][0,204,35],0)
        self.assertEqual(out[3][0,120,120],1)

    def test_download_checksum_failure_preserves_existing_file(self):
        import hashlib,io,tempfile
        from subject_test_pkg.scripts.subject_models import download,verify
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'model.pt';path.write_bytes(b'old')
            with patch('urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
                with self.assertRaises(ValueError):download('https://example.invalid/weight',path,3,hashlib.sha256(b'new').hexdigest())
            self.assertEqual(path.read_bytes(),b'old');self.assertEqual(len(list(path.parent.iterdir())),1)
            with patch('urllib.request.urlopen',return_value=io.BytesIO(b'new')):
                download('https://example.invalid/weight',path,3,hashlib.sha256(b'new').hexdigest())
            self.assertTrue(verify(path,3,hashlib.sha256(b'new').hexdigest()))

    def test_foreground_hint_is_not_a_hard_intersection(self):
        class Dummy:
            model=None
            def __init__(self):self.model=self
            def reset_predictor(self):pass
            def to(self,*a):return self
        hint=self.mask*.2;positive=self.mask.clone()
        with patch('subject_test_pkg.modules.subject.model.load_predictor',return_value=Dummy()),patch('subject_test_pkg.modules.subject.model.predict',return_value=self.mask[0].numpy()):
            out=self.node.clean(self.rgb,segmentation='sam2',foreground_mask=hint,protect_mask=positive,edge_strength=0,feather=0)
        self.assertGreater(out[3].sum(),hint.sum()*4)

    def test_candidate_scoring_prefers_valid_positive_and_negative(self):
        masks=np.stack([np.ones((128,128),bool),self.mask[0].numpy()>.5])
        selected=select_candidate(masks,[.99,.7],self.pos,self.neg)
        self.assertEqual(selected[60,110],0);self.assertEqual(selected[35,50],1)

    def test_missing_model_does_not_download_or_fallback(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'LL_SAM2_MODEL_DIR':temp}):
            with self.assertRaisesRegex(RuntimeError,'缺少本地模型'):load_predictor('sam2.1_hiera_tiny.pt','cpu')
            self.assertEqual(list(Path(temp).iterdir()),[])

    def skin_fixture(self,skin=(.65,.4,.25)):
        rgb=np.zeros((100,100,3),np.float32);rgb[:]=skin;rgb[:,74:80]=[.85,.2,.65]
        mask=np.zeros((100,100),np.float32);mask[10:90,30:80]=1
        core=np.zeros_like(mask,dtype=bool);core[20:80,45:55]=1
        depth=np.ones((100,100),np.float32)*.2;depth[10:90,30:74]=.8
        return rgb,mask,[(mask>.5,core)],depth

    def test_skin_requires_color_and_depth_evidence(self):
        rgb,mask,limbs,depth=self.skin_fixture()
        result,report=skin_cleanup(rgb,mask,limbs,depth,strength=1,band=12,protection=.5)
        self.assertGreater(report['removed'],100);self.assertLess(result[20:80,77:80].mean(),.1)
        self.assertEqual(result[40,50],1)
        depth[:,74:80]=.8
        same,_=skin_cleanup(rgb,mask,limbs,depth,strength=1,band=12,protection=.5)
        np.testing.assert_array_equal(same,mask)

    def test_skin_dark_samples_shadows_and_garments(self):
        rgb,mask,limbs,depth=self.skin_fixture((.19,.11,.07))
        result,report=skin_cleanup(rgb,mask,limbs,depth,strength=1,band=12)
        self.assertGreater(report['sampled_parts'],0)
        self.assertEqual(result[40,50],1)
        rgb[:,30:74]=[.1,.3,.7]
        same,report=skin_cleanup(rgb,mask,limbs,depth,strength=1,band=12)
        self.assertEqual(report['sampled_parts'],0);np.testing.assert_array_equal(same,mask)

    def test_skin_missing_depth_zero_strength_and_empty_hint_skip(self):
        rgb,mask,limbs,depth=self.skin_fixture()
        for kwargs in [dict(depth=None),dict(depth=depth,strength=0),dict(depth=depth,skin_hint=np.zeros_like(mask))]:
            result,report=skin_cleanup(rgb,mask,limbs,**kwargs)
            np.testing.assert_array_equal(result,mask);self.assertEqual(report['removed'],0)

    def test_external_partial_pose_trim_falls_back_to_subject(self):
        points=np.zeros((18,3));points[0]=[60,30,1];points[5]=[50,50,1];points[6]=[50,65,1];points[7]=[50,80,1]
        frame={'canvas_width':128,'canvas_height':128,'people':[{'pose_keypoints_2d':points.flatten().tolist()}]}
        out=self.node.clean(self.rgb,segmentation='external_mask',foreground_mask=self.mask,keypoints=frame,mode='body_trim',edge_strength=0,feather=0)
        self.assertIn('跳过外扩修剪',out[-1]);self.assertLess(out[3].sum(),128*128)


if __name__=='__main__':unittest.main(verbosity=2)
