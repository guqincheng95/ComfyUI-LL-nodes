"""Regression: the whole sole/shoe and palm need more than an ankle/wrist disk."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
import torch
from PIL import Image, ImageDraw
from test_contour import fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('extremity_test_pkg', ROOT/'__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from extremity_test_pkg.modules.contour.geometry import parse_person
from extremity_test_pkg.modules.contour.extremities import extremity_regions, extremity_support
from extremity_test_pkg.modules.contour.processing import build_masks
from extremity_test_pkg.modules.subject.prompts import pose_guides


def sample(kind='barefoot', detailed=False):
    frame, foreground, _ = fixture()
    im = Image.fromarray(np.uint8(foreground*255))
    draw = ImageDraw.Draw(im)
    if kind in ('barefoot', 'shoe'):
        draw.ellipse((42 if kind == 'shoe' else 58, 342, 124, 394), fill=255)
        if detailed:
            frame['people'][0]['foot_keypoints_2d'] = np.array([
                [160,374,1],[142,376,1],[148,350,1],
                [59,378,1],[110,378,1],[92,350,1]],float).ravel().tolist()
    else:
        draw.ellipse((28,180,80,216), fill=255)
        if detailed:
            hand = [[54,182,1]]
            for offset in (-24,-12,0,12,24):
                for step in range(1,5):
                    hand.append([54+offset,182+step*10,1])
            frame['people'][0]['hand_right_keypoints_2d'] = np.array(hand).ravel().tolist()
            for x in (30,42,54,66,78):
                draw.line([(x,193),(x,224)],fill=255,width=7)
    return frame, np.array(im,dtype=np.float32)/255


class ExtremityTests(unittest.TestCase):
    def setUp(self):
        self.node = pkg.NODE_CLASS_MAPPINGS['LLPersonSubjectClean']()

    def clean(self, frame, fg, **options):
        rgb=torch.ones((1,400,240,3))*.5
        return self.node.clean(rgb,segmentation='external_mask',keypoints=frame,
            foreground_mask=torch.from_numpy(fg),mode='body_trim',edge_strength=0,feather=0,**options)

    def test_bare_sole_and_shoe_fallback_recover_old_overtrim(self):
        for kind in ('barefoot','shoe'):
            frame,fg=sample(kind)
            old=self.clean(frame,fg,foot_protection=False)[3][0]
            new=self.clean(frame,fg)[3][0]
            self.assertEqual(old[382,80],0,kind)
            self.assertEqual(new[382,80],1,kind)
            self.assertEqual(new[370,61],1,kind)
            self.assertEqual(new[310,120],0,'inter-leg gap stays empty')
            self.assertEqual(new[204,35],0,'skirt is still trimmed')
            self.assertTrue(np.all(new.numpy()<=fg))

    def test_foot_range_is_independent_of_calf_and_hands(self):
        frame,fg=sample('shoe')
        small=self.clean(frame,fg,foot_scale=.5)[3][0]
        large=self.clean(frame,fg,foot_scale=1.8)[3][0]
        self.assertEqual(small[370,50],0)
        self.assertEqual(large[370,50],1)
        torch.testing.assert_close(small[:280],large[:280])
        self.assertEqual(large[278,96],1)

    def test_detailed_feet_prompt_sam_and_cover_full_sole(self):
        frame,fg=sample('shoe',detailed=True)
        parsed,points,_,_,_=pose_guides((240,400,frame['people']),0,240,400)
        self.assertTrue(any(np.array_equal(p,[59,378]) for p in points))
        parts=extremity_regions(parsed,240,400,foreground=fg)
        feet=[p for p in parts if p['kind']=='foot']
        self.assertEqual([p['source'] for p in feet],['wholebody_landmarks']*2)
        out=self.clean(frame,fg)
        self.assertEqual(out[3][0,378,65],1)
        self.assertEqual(out[3][0,368,45],1,'shoe extends beyond anatomical toe landmarks')
        detail=json.loads(out[-1])['frames'][0]['extremities']
        self.assertTrue(detail['feet_enabled']);self.assertEqual(len(detail['parts']),4)

    def test_palm_and_finger_protection_and_independent_range(self):
        for detailed in (False,True):
            frame,fg=sample('hand',detailed)
            old=self.clean(frame,fg,hand_protection=False)[3][0]
            new=self.clean(frame,fg,hand_scale=1.4)[3][0]
            self.assertEqual(old[201,37],0)
            self.assertEqual(new[201,37],1)
            self.assertTrue(np.all(new.numpy()<=fg))
            if detailed:self.assertEqual(new[220,30],1)
            narrow=self.clean(frame,fg,hand_scale=.5)[3][0]
            self.assertLess(narrow[180:230,:85].sum(),new[180:230,:85].sum())
            torch.testing.assert_close(narrow[280:],new[280:])

    def test_exclusion_wins_and_skin_and_feather_cannot_recut_protected_feet(self):
        frame,fg=sample('shoe')
        depth=torch.linspace(0,1,400)[:,None].expand(400,240)[None,:,:,None].expand(-1,-1,-1,3)
        exclude=torch.zeros((1,400,240));exclude[:,379:385,78:84]=1
        def erase_foot(rgb,mask,*args,**kwargs):
            value=mask.copy();value[330:,:130]=0
            return value,{'skin':'test','removed':int((mask-value).sum()),'sampled_parts':1}
        with patch('extremity_test_pkg.modules.subject.processing.skin_cleanup',side_effect=erase_foot):
            out=self.node.clean(torch.ones((1,400,240,3))*.5,segmentation='external_mask',keypoints=frame,
                foreground_mask=torch.from_numpy(fg),depth_image=depth,mode='body_trim',
                edge_strength=1,skin_enabled=True,feather=3,exclude_mask=exclude,failure_policy='keep_subject')
        self.assertEqual(out[3][0,370,61],1)
        self.assertEqual(out[3][0,382,80],0)
        self.assertEqual(out[5][0,370,61],0,'skin deletion diagnostic excludes restored pixels')
        self.assertNotIn('fallback',json.loads(out[-1])['frames'][0])
        torch.testing.assert_close(out[2],depth*out[3][...,None])

    def test_shoe_color_and_skin_color_do_not_change_whole_foot_protection(self):
        frame,fg=sample('shoe')
        depth=torch.from_numpy(fg)[None,:,:,None].expand(-1,-1,-1,3)*.6+.2
        for color in ([.7,.45,.3],[.1,.15,.8],[.03,.03,.03]):
            rgb=torch.ones((1,400,240,3))*.5;rgb[:,342:395,40:125]=torch.tensor(color)
            out=self.node.clean(rgb,segmentation='external_mask',keypoints=frame,
                foreground_mask=torch.from_numpy(fg),depth_image=depth,mode='body_trim',edge_strength=1)
            self.assertEqual(out[3][0,382,80],1)
            torch.testing.assert_close(out[0][0,382,80],rgb[0,382,80])
            torch.testing.assert_close(out[2][0,382,80],depth[0,382,80])

    def test_new_options_append_after_old_widgets_and_legacy_calls_remain_valid(self):
        schema=self.node.INPUT_TYPES()
        old=['segmentation','model_name','device','mode','person_index','confidence','analysis_size',
             'edge_strength','depth_weight','edge_band','trim_scale','skin_enabled','skin_strength',
             'skin_band','skin_protection','feather','rgb_background','failure_policy']
        native=[name for name,definition in schema['required'].items() if name!='image']
        self.assertEqual(native,old)
        appended=['foot_protection','foot_scale','hand_protection','hand_scale']
        self.assertEqual(list(schema['optional'])[-4:],appended)
        for cls in pkg.NODE_CLASS_MAPPINGS['LLPersonSubjectClean'],pkg.NODE_CLASS_MAPPINGS['LLPersonContourTrim']:
            self.assertEqual(list(cls.INPUT_TYPES()['optional'])[-4:],appended)

    def test_initial_missing_foot_cannot_be_painted_back(self):
        frame,fg=sample('shoe');fg[376:,30:130]=0
        out=self.clean(frame,fg,foot_scale=3)
        self.assertEqual(out[3][0,382,80],0)
        self.assertTrue(np.all(out[3][0].numpy()<=fg))

    def test_legacy_node_also_has_independent_hand_and_foot_controls(self):
        frame,fg=sample('shoe')
        before,_=build_masks(frame,1,400,240,foreground_mask=fg,padding_px=0,feather_px=0,foot_protection=False)
        after,report=build_masks(frame,1,400,240,foreground_mask=fg,padding_px=0,feather_px=0)
        self.assertEqual(before[0,382,80],0);self.assertEqual(after[0,382,80],1)
        self.assertIn('脚掌2处',report)
        exclude=np.zeros_like(fg);exclude[382,80]=1
        mask,_=build_masks(frame,1,400,240,foreground_mask=fg,exclude_mask=exclude)
        self.assertEqual(mask[0,382,80],0)

    def test_body25_feet_mapping_null_optional_parts_and_normalized_coordinates(self):
        frame,fg=sample(detailed=True);person=copy.deepcopy(frame['people'][0])
        body=np.array(person['pose_keypoints_2d']).reshape(-1,3)
        feet=np.array(person['foot_keypoints_2d']).reshape(-1,3)
        body25=np.zeros((25,3));body25[list((0,1,2,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18))]=body
        body25[19:25]=feet
        p={'pose_keypoints_2d':body25.ravel().tolist(),'foot_keypoints_2d':None,
           'hand_left_keypoints_2d':None,'hand_right_keypoints_2d':None,'face_keypoints_2d':None}
        parsed=parse_person(p,(240,400),(240,400))
        np.testing.assert_array_equal(parsed['foot_keypoints_2d'],feet)
        for key in ('pose_keypoints_2d','foot_keypoints_2d'):
            a=body25.copy() if key=='pose_keypoints_2d' else feet.copy();a[:,:2]/=[240,400]
            p[key]=a.ravel().tolist()
        normalized=parse_person(p,(240,400),(240,400))
        np.testing.assert_allclose(normalized['foot_keypoints_2d'],feet)

    def test_no_pose_or_missing_endpoints_skips_without_inventing_regions(self):
        self.assertEqual(extremity_regions(None,240,400),[])
        frame,fg=sample();parsed=parse_person(frame['people'][0],(240,400),(240,400))
        parsed['body'][[4,7,10,13]]=np.nan
        self.assertEqual(extremity_regions(parsed,240,400,foreground=fg),[])
        out=self.node.clean(torch.ones((1,400,240,3))*.5,segmentation='external_mask',
                            foreground_mask=torch.from_numpy(fg),edge_strength=0,feather=0)
        self.assertEqual(json.loads(out[-1])['frames'][0]['extremities']['parts'],[])

    def test_broadcast_soft_alpha_and_invalid_controls(self):
        frame,fg=sample('shoe');fg*=.75
        rgb=torch.ones((2,400,240,3))*.5;alpha=torch.ones((2,400,240,1))*.6
        image=torch.cat([rgb,alpha],-1)
        out=self.node.clean(image,segmentation='external_mask',keypoints=frame,
            foreground_mask=torch.from_numpy(fg),edge_strength=0,feather=0,mode='body_trim')
        torch.testing.assert_close(out[3][0],out[3][1])
        self.assertAlmostEqual(float(out[3][0,382,80]),.45,places=5)
        for opts in [dict(foot_scale=float('nan')),dict(hand_scale=4),dict(foot_protection=1),dict(hand_protection='true')]:
            with self.assertRaises(ValueError):self.clean(frame,fg,**opts)
            with self.assertRaises(ValueError):build_masks(frame,1,400,240,**opts)


if __name__=='__main__':unittest.main(verbosity=2)
