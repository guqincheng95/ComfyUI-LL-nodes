"""Regression for incoming RMBG mattes, semantic garment/headwear cuts and setup."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pruning_test_pkg',ROOT/'__init__.py')
pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from pruning_test_pkg.modules.subject.pruning import semantic_cuts,feather_new_cuts,torso_bridge
from pruning_test_pkg.modules.subject.parsing import probabilities,load_parser


class PruningTests(unittest.TestCase):
    def setUp(self):
        self.node=pkg.NODE_CLASS_MAPPINGS['LLPersonSubjectClean']()
        self.mask=torch.zeros((1,256,128));self.mask[:,20:240,40:90]=1
        self.mask[:,80:85,12:40]=.25;self.mask[:,85:90,14:40]=.7
        self.color=torch.tensor([.8,.5,.3])[None,None,None,:].expand(1,256,128,3)

    def run_cutout(self,mask=None,**kwargs):
        mask=self.mask if mask is None else mask
        image=self.color*mask[...,None]
        kwargs={'input_image_mode':'cutout_black',**kwargs}
        return self.node.clean(image,segmentation='external_mask',foreground_mask=mask,
            **kwargs)

    def test_rmbg_soft_hand_matte_and_pixels_are_identity_without_new_cuts(self):
        out=self.run_cutout(edge_strength=.7,feather=3)
        torch.testing.assert_close(out[3],self.mask,rtol=0,atol=1e-7)
        torch.testing.assert_close(out[0],self.color*self.mask[...,None],rtol=0,atol=1e-7)
        self.assertEqual(float(out[3][0,82,20]),.25)

    def test_native_thin_fingers_survive_analysis_downscale(self):
        mask=torch.zeros((1,1024,512));mask[:,60:990,200:350]=1
        mask[:,400,50:200]=.35;mask[:,405,60:200]=.7
        color=torch.tensor([.7,.5,.3])[None,None,None,:]
        image=mask[...,None]*color
        out=self.node.clean(image,segmentation='external_mask',foreground_mask=mask,
            input_image_mode='cutout_black',analysis_size=256,feather=4)
        torch.testing.assert_close(out[3],mask,rtol=0,atol=1e-7)
        torch.testing.assert_close(out[0],image,rtol=0,atol=1e-7)

    def test_black_and_white_cutouts_do_not_apply_alpha_twice(self):
        for background,mode in [(0.,'cutout_black'),(1.,'cutout_white')]:
            image=self.color*self.mask[...,None]+background*(1-self.mask[...,None])
            out=self.node.clean(image,segmentation='external_mask',foreground_mask=self.mask,
                input_image_mode=mode,rgb_background='white' if background else 'black',feather=0)
            torch.testing.assert_close(out[0],image,rtol=0,atol=2e-7)
            torch.testing.assert_close(out[3],self.mask,rtol=0,atol=1e-7)

    def test_soft_exclusion_applies_opacity_once(self):
        exclude=torch.zeros_like(self.mask);exclude[:,100:110,50:60]=.5
        out=self.run_cutout(edge_strength=0,feather=0,exclude_mask=exclude)
        self.assertEqual(float(out[3][0,105,55]),.5)
        torch.testing.assert_close(out[0][0,105,55],self.color[0,105,55]*.5)

    def test_new_cut_feathers_but_original_soft_boundary_does_not(self):
        initial=self.mask[0].numpy();keep=initial.copy();keep[120:,:]=0
        result=feather_new_cuts(initial,keep,2)
        np.testing.assert_array_equal(result[80:90],initial[80:90])
        self.assertTrue(0<result[119,60]<1)
        self.assertEqual(result[130,60],0)

    def parts_fixture(self):
        body=np.zeros((256,128),np.float32);body[20:240,40:90]=1
        garment=np.zeros_like(body);garment[110:210,80:125]=1
        head=np.zeros_like(body);head[25:40,90:105]=1
        initial=np.maximum(np.maximum(body,garment),head)
        return initial,{'body':body,'garment':garment,'accessory':head,'labels':None,'source':'test supplied masks'}

    def test_semantic_garment_and_headwear_removed_body_and_hand_kept(self):
        fg,parts=self.parts_fixture();fg[80:90,12:40]=1;parts['body'][80:90,12:40]=1
        out=self.node.clean(torch.from_numpy(fg)[None,:,:,None].expand(-1,-1,-1,3)*.7,
            segmentation='external_mask',foreground_mask=torch.from_numpy(fg),semantic_pruning='external_masks',
            body_part_mask=torch.from_numpy(parts['body']),garment_mask=torch.from_numpy(parts['garment']),
            headwear_mask=torch.from_numpy(parts['accessory']),mode='body_trim',garment_margin=.05,feather=0)
        self.assertEqual(float(out[3][0,150,120]),0)
        self.assertEqual(float(out[3][0,30,98]),0)
        self.assertEqual(float(out[3][0,85,20]),1)
        self.assertEqual(float(out[3][0,180,60]),1)
        self.assertGreater(json.loads(out[-1])['frames'][0]['semantic_pruning']['headwear_removed_pixels'],0)

    def test_explicit_protect_overrides_semantic_cut_exclude_still_wins(self):
        fg,parts=self.parts_fixture();protect=torch.zeros((1,256,128));protect[:,25:40,90:105]=1
        exclude=torch.zeros_like(protect);exclude[:,30,98]=1
        out=self.node.clean(torch.ones((1,256,128,3))*.5,segmentation='external_mask',
            foreground_mask=torch.from_numpy(fg),semantic_pruning='external_masks',body_part_mask=torch.from_numpy(parts['body']),
            headwear_mask=torch.from_numpy(parts['accessory']),protect_mask=protect,exclude_mask=exclude,edge_strength=0,feather=0)
        self.assertEqual(float(out[3][0,29,98]),1);self.assertEqual(float(out[3][0,30,98]),0)

    def test_headwear_switch_off_and_person_mode_keep_garments(self):
        fg,parts=self.parts_fixture()
        cut,_,detail=semantic_cuts(fg,parts,mode='person',remove_headwear=False)
        self.assertFalse(cut.any());self.assertEqual(detail['headwear_removed_pixels'],0)

    def test_head_only_samples_do_not_delete_whole_dress(self):
        fg,parts=self.parts_fixture();parts['body'][70:]=0
        cut,_,detail=semantic_cuts(fg,parts,mode='body_trim',remove_headwear=False)
        self.assertFalse(cut.any());self.assertIn('跳过',detail['garment'])

    def test_no_garment_means_no_spurious_top_left_cut(self):
        fg,parts=self.parts_fixture();parts['garment'][:]=0;parts['accessory'][:]=0
        cut,_,detail=semantic_cuts(fg,parts)
        self.assertFalse(cut.any());self.assertIn('没有可剪衣料',detail['garment'])

    def test_partial_pose_can_run_semantic_pruning_instead_of_global_skip(self):
        fg,parts=self.parts_fixture();body=np.zeros((18,3));body[0]=[60,30,1]
        frame={'canvas_width':128,'canvas_height':256,'people':[{'pose_keypoints_2d':body.ravel().tolist()}]}
        out=self.node.clean(torch.ones((1,256,128,3))*.5,segmentation='external_mask',foreground_mask=torch.from_numpy(fg),
            keypoints=frame,confidence=.6,semantic_pruning='external_masks',headwear_mask=torch.from_numpy(parts['accessory']),
            edge_strength=0,feather=0)
        self.assertEqual(float(out[3][0,30,98]),0);self.assertIn('有效骨架提示不足',out[-1])

    def test_whole_person_skin_hint_is_reported_and_ignored(self):
        out=self.run_cutout(skin_enabled=True,skin_mask=self.mask,edge_strength=0,feather=0)
        self.assertIn('疑似误接整人RMBG MASK',out[-1]);torch.testing.assert_close(out[3],self.mask)

    def test_missing_model_never_downloads_and_off_never_loads_parser(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'LL_PARTS_MODEL':str(Path(folder)/'missing.onnx')}),patch('urllib.request.urlopen') as network:
            with self.assertRaisesRegex(RuntimeError,'缺少本地人体部位ONNX模型'):load_parser()
            (Path(folder)/'missing.onnx').write_bytes(b'wrong 18-class model')
            with self.assertRaisesRegex(RuntimeError,'SHA256不符'):load_parser()
            network.assert_not_called()
        with patch('pruning_test_pkg.modules.subject.parsing.load_parser',side_effect=AssertionError('must stay off')):
            self.run_cutout(semantic_pruning='off',feather=0)

    def test_parser_normalization_contract_and_wrong_class_count(self):
        class Input:name='pixel_values'
        class Session:
            def get_inputs(self):return [Input()]
            def run(self,names,inputs):
                x=inputs['pixel_values'];self.x=x
                result=np.zeros((1,18,8,8),np.float32);result[:,2]=8
                return [result]
        session=Session();p=probabilities(session,np.ones((30,20,3),np.float32)*.5)
        self.assertEqual(p.shape,(18,30,20));self.assertTrue((p.argmax(0)==2).all())
        self.assertEqual(session.x.shape,(1,3,512,512));np.testing.assert_allclose(p.sum(0),1,atol=1e-6)
        with patch.object(session,'run',return_value=[np.zeros((1,19,8,8))]):
            with self.assertRaises(ValueError):probabilities(session,np.ones((30,20,3),np.float32))

    def test_input_validation_and_external_masks_require_real_parts(self):
        for options in [dict(input_image_mode='bad'),dict(preserve_foreground=1),dict(semantic_pruning='bad'),dict(garment_margin=2),dict(remove_headwear=1),
                        dict(semantic_pruning='external_masks'),dict(semantic_pruning='external_masks',garment_mask=self.mask)]:
            with self.assertRaises(ValueError):self.run_cutout(**options)
        with self.assertRaisesRegex(ValueError,'需要foreground_mask'):
            self.node.clean(self.color,input_image_mode='cutout_black')

    def test_old_widget_prefix_is_preserved_new_controls_append(self):
        s=self.node.INPUT_TYPES();optional=list(s['optional'])
        self.assertEqual(optional[:10],['depth_image','keypoints','foreground_mask','protect_mask','exclude_mask','skin_mask',
                                      'foot_protection','foot_scale','hand_protection','hand_scale'])
        self.assertEqual(optional[10:15],['input_image_mode','preserve_foreground','semantic_pruning','remove_headwear','garment_margin'])


if __name__=='__main__':unittest.main(verbosity=2)
