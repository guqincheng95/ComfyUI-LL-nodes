import importlib.util
from pathlib import Path
import sys
import unittest
import torch
import torch.nn.functional as F

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('color_match_test_pkg',ROOT/'__init__.py')
pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from color_match_test_pkg.modules.photo.color_match import match_image,linear_to_oklab,oklab_to_linear,_tone_curve,_interpolate,_sample
from color_match_test_pkg.modules.photo.processing import srgb_to_linear,linear_to_srgb,adjust_image

torch.set_num_threads(2)


class ColorMatchTests(unittest.TestCase):
    def setUp(self):
        self.original=.12+.65*torch.rand((1,39,57,3),generator=torch.Generator().manual_seed(16))
        linear=srgb_to_linear(self.original)
        self.changed=linear_to_srgb(linear*torch.tensor([1.18,.87,1.07])+torch.tensor([.012,.006,-.003])).clamp(0,1)

    def test_original_corrects_linear_rgb_cast(self):
        corrected=match_image(self.changed,self.original,'original')
        before=(self.changed-self.original).square().mean()
        after=(corrected-self.original).square().mean()
        self.assertLess(after,before*.02)

    def test_upscaled_input_retains_shape_and_restores_color(self):
        up=lambda a:F.interpolate(a.permute(0,3,1,2),scale_factor=2,mode='bilinear',align_corners=False).permute(0,2,3,1)
        target=linear_to_srgb(srgb_to_linear(up(self.original))*torch.tensor([1.12,.9,1.05])+.005)
        corrected=match_image(target,self.original,'original')
        self.assertEqual(corrected.shape,target.shape)
        self.assertLess((corrected-up(self.original)).square().mean(),(target-up(self.original)).square().mean()*.1)

    def test_reference_matches_luminance_and_chroma_statistics(self):
        # A continuous ramp provides all three tonal regions without clipping.
        x=torch.linspace(.08,.9,9000).reshape(1,100,30,3)
        lab=linear_to_oklab(srgb_to_linear(x));ref=lab.clone()
        ref[...,0]=ref[...,0].pow(.87)
        ref[...,1]+=.018;ref[...,2]+=.025
        ref=linear_to_srgb(oklab_to_linear(ref).clamp(0,1)).clamp(0,1)
        result=match_image(x,ref,'reference')
        measure=lambda a:linear_to_oklab(srgb_to_linear(a)).mean((0,1,2))
        self.assertLess((measure(result)-measure(ref)).abs().mean(),(measure(x)-measure(ref)).abs().mean()*.3)

    def test_modes_zero_identity_and_same_image(self):
        self.assertIs(match_image(self.changed,None,'off'),self.changed)
        self.assertIs(match_image(self.changed,None,'original',match_strength=0),self.changed)
        self.assertIs(match_image(self.original,self.original,'reference'),self.original)
        self.assertIs(match_image(self.changed,None,'reference',match_luminance=0,match_color=0),self.changed)

    def test_luminance_only_and_color_only_are_separate(self):
        before=linear_to_oklab(srgb_to_linear(self.changed))
        color_only=linear_to_oklab(srgb_to_linear(match_image(self.changed,self.original,'original',match_luminance=0)))
        tone_only=linear_to_oklab(srgb_to_linear(match_image(self.changed,self.original,'original',match_color=0)))
        self.assertLess((color_only[...,0]-before[...,0]).abs().max(),2e-6)
        self.assertLess((tone_only[...,1:]-before[...,1:]).abs().max(),2e-6)

    def test_strength_and_alpha_nonmutation(self):
        alpha=torch.rand_like(self.changed[...,:1]);target=torch.cat([self.changed,alpha],-1)
        old=target.clone();ref=torch.cat([self.original,torch.ones_like(alpha)],-1)
        half=match_image(target,ref,'original',match_strength=.5)
        full=match_image(target,ref,'original')
        self.assertTrue(torch.equal(target,old));self.assertTrue(torch.equal(full[...,3:],alpha))
        self.assertGreater((half[...,:3]-self.original).square().mean(),(full[...,:3]-self.original).square().mean())
        self.assertLess((half[...,:3]-self.original).square().mean(),(target[...,:3]-self.original).square().mean())

    def test_batch_broadcast_and_per_frame_reference(self):
        target=self.changed.repeat(2,1,1,1)
        reference=self.original.repeat(2,1,1,1)
        a=match_image(target,self.original,'original');b=match_image(target,reference,'original')
        torch.testing.assert_close(a,b)
        with self.assertRaises(ValueError):match_image(target,reference.repeat(2,1,1,1),'reference')

    def test_uniform_grayscale_and_clipped_images_remain_finite(self):
        for value in (0.,.5,1.):
            image=torch.full((1,8,8,3),value)
            result=match_image(image,self.original,'reference')
            self.assertTrue(torch.isfinite(result).all());self.assertGreaterEqual(result.min(),0);self.assertLessEqual(result.max(),1)
            self.assertLess(result.std(),.15)
            self.assertTrue(torch.equal(result[:,0],result[:,1]))
        source=torch.linspace(0,1,100).reshape(1,10,10,1).repeat(1,1,1,3)
        x,y=_tone_curve(source.flatten(),source.pow(.8).flatten())
        mapped=_interpolate(torch.linspace(0,1,1000),x,y)
        self.assertTrue((mapped[1:]-mapped[:-1]>=-1e-7).all())
        self.assertEqual(mapped[0],0);self.assertEqual(mapped[-1],1)

    def test_manual_adjustments_follow_matching_and_old_call_works(self):
        node=pkg.NODE_CLASS_MAPPINGS['AIVisualPhotoFinish']()
        actual=node.apply(self.changed,reference_image=self.original,auto_mode='original',exposure=.3)[0]
        expected=adjust_image(match_image(self.changed,self.original,'original'),exposure=.3)
        torch.testing.assert_close(actual,expected)
        self.assertIs(node.apply(self.original)[0],self.original)
        schema=node.INPUT_TYPES()
        self.assertNotIn('auto_mode',schema['required'])
        self.assertIn('reference_image',schema['optional'])

    def test_invalid_controls_inputs_and_aspect_ratio(self):
        for kwargs in [dict(auto_mode='no'),dict(match_strength=-1),dict(match_color=float('nan')),dict(match_luminance=True),dict(tile_rows=0)]:
            with self.assertRaises(ValueError):match_image(self.changed,self.original,**kwargs)
        with self.assertRaises(ValueError):match_image(self.changed,None,'reference')
        with self.assertRaises(ValueError):match_image(self.changed,torch.rand(1,20,20,3),'original')
        self.assertEqual(match_image(self.changed,torch.rand(1,20,20,3),'reference').shape,self.changed.shape)
        bad=self.changed.clone();bad[0,0,0,0]=float('nan')
        with self.assertRaises(ValueError):match_image(bad,self.original,'original')

    def test_transparent_pixels_ignored_and_float_precision(self):
        target=torch.cat([self.changed,torch.ones_like(self.changed[...,:1])],-1)
        reference=torch.cat([self.original,torch.ones_like(self.original[...,:1])],-1)
        target[:,0,:,3]=0;reference[:,0,:,3]=0
        result=match_image(target.half(),reference,'original')
        self.assertTrue(torch.isfinite(result).all());self.assertEqual(result.dtype,torch.float32)
        self.assertGreater(torch.unique(result[...,0]).numel(),256)
        target[...,3]=0;self.assertTrue(torch.equal(match_image(target,reference,'reference'),target))

    def test_oklab_roundtrip_and_tile_invariance(self):
        linear=srgb_to_linear(self.original)
        torch.testing.assert_close(oklab_to_linear(linear_to_oklab(linear)),linear,atol=1e-6,rtol=0)
        a=match_image(self.changed,self.original,'original',tile_rows=5)
        b=match_image(self.changed,self.original,'original',tile_rows=128)
        torch.testing.assert_close(a,b,atol=2e-6,rtol=0)

    def test_transparent_hidden_rgb_does_not_bleed_into_statistics(self):
        image=torch.zeros((300,400,4))
        image[80:220,100:300,:3]=torch.tensor([.2,.5,.7])
        image[80:220,100:300,3]=1
        other=image.clone();other[image[...,3]==0,:3]=torch.tensor([1.,0.,1.])
        a,b=_sample(image),_sample(other)
        torch.testing.assert_close(a,b,atol=0,rtol=0)


if __name__=='__main__':unittest.main(verbosity=2)
