import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import warnings

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('contour_test_pkg', ROOT / '__init__.py')
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
from contour_test_pkg.modules.contour.processing import build_masks
from contour_test_pkg.modules.contour.geometry import parse_person, observed_width


def fixture():
    # Independent silhouette fixture: body, detached head ornament, broad peplum.
    w, h = 240, 400
    xy = [(120, 48), (120, 90), (88, 96), (66, 142), (54, 182), (152, 96), (174, 142), (186, 182),
          (100, 204), (96, 278), (92, 358), (140, 204), (144, 278), (148, 358),
          (112, 43), (128, 43), (102, 48), (138, 48)]
    body = np.array([[x, y, 1.0] for x, y in xy])
    person = {'pose_keypoints_2d': body.flatten().tolist()}
    source = Image.new('L', (w, h)); d = ImageDraw.Draw(source)
    d.ellipse((98, 21, 142, 78), fill=255)
    d.rectangle((83, 90, 157, 216), fill=255)
    for x in [99, 141]: d.line([(x, 205), (x, 360)], fill=255, width=29)
    for points in [[(88,96),(66,142),(54,182)],[(152,96),(174,142),(186,182)]]:
        d.line(points, fill=255, width=21)
    for x in [54,186]: d.ellipse((x-10,176,x+10,199), fill=255)
    for x in [92,148]: d.ellipse((x-12,350,x+14,375), fill=255)
    d.polygon([(83,170),(20,202),(70,230),(170,230),(220,202),(157,170)],fill=255)
    d.rectangle((165,12,185,65),fill=255)  # false head ornament connected by ribbon
    d.line([(130,35),(174,26)],fill=255,width=5)
    foreground = np.array(source,dtype=np.float32)/255
    y,x = np.mgrid[:h,:w]
    depth = (0.2 + x / (w*3) + y / (h*3)).astype(np.float32)*foreground
    frame = {'canvas_width':w,'canvas_height':h,'people':[person]}
    return frame, foreground, np.repeat(depth[None,...,None],3,axis=3)


class ContourTests(unittest.TestCase):
    def setUp(self): self.frame,self.fg,self.image=fixture()

    def test_trims_protrusions_keeps_body_and_canvas(self):
        mask,report=build_masks(self.frame,1,400,240,foreground_mask=self.fg,padding_px=0,feather_px=0)
        self.assertEqual(mask.shape,(1,400,240))
        self.assertEqual(mask[0,40,174],0)  # ornament
        self.assertEqual(mask[0,204,35],0)  # outer skirt
        for y,x in [(50,120),(120,120),(200,120),(275,96),(340,148),(142,66)]:
            self.assertEqual(mask[0,y,x],1,(y,x))
        self.assertEqual(mask[0,310,120],0) # original inter-leg gap never filled
        self.assertTrue(np.all(mask[0]<=self.fg))
        self.assertIn('1 帧完成',report)

    def test_observations_fit_narrow_body_without_accepting_huge_skirt(self):
        fg=np.zeros((80,80),np.float32);fg[:,34:47]=1
        small=observed_width(fg,[np.array([40.,40.])],np.array([1.,0.]),10)
        self.assertLess(small,10)
        fg[:]=1
        self.assertEqual(observed_width(fg,[np.array([40.,40.])],np.array([1.,0.]),10),10)

    def test_sdpose_pixel_and_normalized_and_body25(self):
        pixel=parse_person(self.frame['people'][0],(240,400),(240,400))['body']
        p=copy.deepcopy(self.frame['people'][0]);a=np.array(p['pose_keypoints_2d']).reshape(-1,3);a[:,:2]/=[240,400];p['pose_keypoints_2d']=a.flatten().tolist()
        normalized=parse_person(p,(240,400),(240,400))['body']
        np.testing.assert_allclose(pixel,normalized)
        mapping=(0,1,2,3,4,5,6,7,9,10,11,12,13,14,15,16,17,18)
        b=np.zeros((25,3));b[list(mapping)]=pixel
        p={'pose_keypoints_2d':b.flatten().tolist()}
        np.testing.assert_allclose(parse_person(p,(240,400),(240,400))['body'],pixel)

    def test_keypoint_canvas_scales_without_changing_layout(self):
        f=copy.deepcopy(self.frame);f['canvas_width']*=2;f['canvas_height']*=2
        a=np.array(f['people'][0]['pose_keypoints_2d']).reshape(-1,3);a[:,:2]*=2;f['people'][0]['pose_keypoints_2d']=a.flatten().tolist()
        first,_=build_masks(self.frame,1,400,240)
        second,_=build_masks(f,1,400,240)
        np.testing.assert_array_equal(first,second)

    def test_protect_exclude_priority_and_foreground_intersection(self):
        protect=np.zeros((400,240));protect[40,174]=1;protect[0,0]=1
        exclude=np.zeros((400,240));exclude[120,120]=1;exclude[40,174]=1
        mask,_=build_masks(self.frame,1,400,240,foreground_mask=self.fg,protect_mask=protect)
        self.assertEqual(mask[0,40,174],1);self.assertEqual(mask[0,0,0],0)
        mask,_=build_masks(self.frame,1,400,240,foreground_mask=self.fg,protect_mask=protect,exclude_mask=exclude)
        self.assertEqual(mask[0,120,120],0);self.assertEqual(mask[0,40,174],0)

    def test_missing_keypoints_keep_frame_and_error_mode(self):
        missing=copy.deepcopy(self.frame);missing['people'][0]['pose_keypoints_2d'][4*3+2]=0
        mask,report=build_masks(missing,1,400,240,foreground_mask=self.fg)
        np.testing.assert_array_equal(mask[0],self.fg)
        self.assertIn('未修剪',report)
        with self.assertRaises(ValueError):build_masks(missing,1,400,240,missing_pose='error')
        empty={**self.frame,'people':[]}
        mask,_=build_masks(empty,1,400,240)
        self.assertTrue(np.all(mask==1))

    def test_batches_broadcast_validation_and_no_input_mutation(self):
        old=copy.deepcopy(self.frame);old_fg=self.fg.copy()
        mask,report=build_masks([self.frame],2,400,240,foreground_mask=self.fg)
        np.testing.assert_array_equal(mask[0],mask[1]);self.assertIn('单帧骨架',report)
        with self.assertRaises(ValueError):build_masks([self.frame]*3,2,400,240)
        with self.assertRaises(ValueError):build_masks(self.frame,1,400,240,foreground_mask=np.zeros((3,400,240)))
        with self.assertRaises(ValueError):build_masks(self.frame,1,400,240,exclude_mask=np.full((400,240),np.nan))
        self.assertEqual(self.frame,old);np.testing.assert_array_equal(self.fg,old_fg)

    def test_foreground_resolution_alignment_and_crop_mismatch(self):
        smaller = np.asarray(Image.fromarray(self.fg).resize((120,200),Image.Resampling.BILINEAR))
        mask,report=build_masks(self.frame,1,400,240,foreground_mask=smaller)
        self.assertEqual(mask.shape,(1,400,240))
        self.assertEqual(mask[0,120,120],1)
        self.assertEqual(mask[0,40,174],0)
        self.assertIn('等比例遮罩',report)
        with self.assertRaises(ValueError):build_masks(self.frame,1,400,240,foreground_mask=np.ones((200,200)))

    def test_temporal_state_is_local_and_large_jump_resets(self):
        first=copy.deepcopy(self.frame);last=copy.deepcopy(self.frame)
        a=np.array(last['people'][0]['pose_keypoints_2d']).reshape(-1,3);a[:,0]+=90
        last['people'][0]['pose_keypoints_2d']=a.flatten().tolist()
        mask,_=build_masks([first,last],2,400,240,temporal_smoothing=.8)
        independent,_=build_masks(last,1,400,240,temporal_smoothing=.8)
        np.testing.assert_array_equal(mask[1],independent[0])
        again,_=build_masks(first,1,400,240,temporal_smoothing=.8)
        baseline,_=build_masks(first,1,400,240)
        np.testing.assert_array_equal(again,baseline)

    def test_scale_controls_and_feather_preserve_range(self):
        narrow,_=build_masks(self.frame,1,400,240,head_scale=.7,arm_scale=.7,padding_px=0)
        wide,_=build_masks(self.frame,1,400,240,head_scale=1.3,arm_scale=1.3,padding_px=0)
        self.assertLess(narrow.sum(),wide.sum())
        self.assertGreater(np.count_nonzero((wide>0)&(wide<1)),0)
        self.assertGreaterEqual(wide.min(),0);self.assertLessEqual(wide.max(),1)
        for opts in [dict(padding_px=-1),dict(head_scale=float('nan')),dict(person_index=True),dict(unknown=1)]:
            with self.assertRaises(ValueError):build_masks(self.frame,1,400,240,**opts)

    def test_multiple_people_and_person_index(self):
        f=copy.deepcopy(self.frame);f['people'].append(copy.deepcopy(f['people'][0]))
        a=np.array(f['people'][1]['pose_keypoints_2d']).reshape(-1,3);a[:,0]+=55;f['people'][1]['pose_keypoints_2d']=a.flatten().tolist()
        all_mask,_=build_masks(f,1,400,240,person_index=-1)
        one,_=build_masks(f,1,400,240)
        self.assertGreater(all_mask.sum(),one.sum())
        selected,_=build_masks(f,1,400,240,person_index=1)
        self.assertGreater(selected[0,120,175],0)

    def test_node_tensor_precision_alpha_and_outputs(self):
        import torch
        node=pkg.NODE_CLASS_MAPPINGS['LLPersonContourTrim']()
        image=torch.from_numpy(self.image)
        old=image.clone()
        result,mask,preview,report=node.trim(image,self.frame,foreground_mask=torch.from_numpy(self.fg),padding_px=0,feather_px=0)
        self.assertEqual(result.shape,image.shape);self.assertEqual(preview.shape,image.shape)
        self.assertEqual(mask.shape,(1,400,240))
        self.assertTrue(torch.equal(image,old))
        self.assertTrue(torch.equal(result[mask==1],image[mask==1]))
        self.assertEqual(torch.count_nonzero(result[mask==0]),0)
        self.assertGreater(torch.unique(result[...,0]).numel(),256)
        rgba=torch.cat([image,torch.ones_like(image[...,:1])*.6],-1).half()
        out,mask,_,_=node.trim(rgba,self.frame,padding_px=0,feather_px=0)
        self.assertEqual(out.dtype,torch.float16)
        self.assertTrue(torch.equal(out[...,3],rgba[...,3]*mask.half()))

    def test_invalid_input_contracts(self):
        for invalid in ['image',[],{'people':[]}]:
            with self.assertRaises(ValueError):build_masks(invalid,1,400,240)
        p=copy.deepcopy(self.frame);p['people'][0]['pose_keypoints_2d']=[0]*17
        with self.assertRaises(ValueError):build_masks(p,1,400,240)
        f=copy.deepcopy(self.frame);f['people'][0]['pose_keypoints_2d']=f['people'][0]['pose_keypoints_2d'][:51]
        with self.assertRaises(ValueError):build_masks(f,1,400,240)


if __name__=='__main__':unittest.main(verbosity=2)
