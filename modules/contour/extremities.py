"""Local hand/whole-foot envelopes, clipped to observed foreground when available.

Uses the existing OpenPose coordinates and Pillow rasterization. No new detector,
skin classifier, inpainting, or hidden-body reconstruction is introduced.
"""
import numpy as np
from PIL import Image, ImageDraw


def _valid(point):
    return len(point) >= 2 and np.isfinite(point[:2]).all()


def _hull(points):
    points = sorted(set(map(tuple, points)))
    if len(points) < 3:
        return points
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower, upper = [], []
    for chain, order in ((lower, points), (upper, reversed(points))):
        for point in order:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
    return lower[:-1]+upper[:-1]


def extremity_regions(parsed, width, height, *, foreground=None,
                       foot_protection=True, foot_scale=1.2,
                       hand_protection=True, hand_scale=1.15):
    """Return bounded local regions and their observed support, one per extremity.

    Detailed landmarks outline the entire sole/shoe or palm/fingers. If they are
    missing, a local endpoint envelope is used, not a tiny ankle/wrist disk.
    Enlarging a region never grows support outside the supplied foreground.
    """
    if parsed is None or len(parsed.get('body', [])) != 18:
        return []
    body = parsed['body']
    core = (2, 5, 8, 11)
    torso = (np.linalg.norm(body[[8, 11], :2].mean(0)-body[[2, 5], :2].mean(0))
             if all(_valid(body[i]) for i in core) else max(width, height)*.22)
    torso = max(float(torso), 6.)
    feet = parsed.get('foot_keypoints_2d', np.empty((0, 3)))
    definitions = []
    if foot_protection:
        for side, anchor, parent, start in [('left', 13, 12, 0), ('right', 10, 9, 3)]:
            definitions.append(('foot', side, anchor, parent, feet[start:start+3], foot_scale))
    if hand_protection:
        for side, anchor, parent in [('left', 7, 6), ('right', 4, 3)]:
            definitions.append(('hand', side, anchor, parent,
                                parsed.get('hand_'+side+'_keypoints_2d', np.empty((0, 3))), hand_scale))
    results = []
    for kind, side, anchor_index, parent_index, landmarks, scale in definitions:
        if not _valid(body[anchor_index]):
            continue
        anchor = body[anchor_index, :2]
        if not (0 <= anchor[0] < width and 0 <= anchor[1] < height):
            continue
        points = np.asarray([p[:2] for p in landmarks if _valid(p)
                             and 0 <= p[0] < width and 0 <= p[1] < height], dtype=float).reshape(-1, 2)
        image = Image.new('L', (width, height))
        draw = ImageDraw.Draw(image)
        detailed = len(points) >= (2 if kind == 'foot' else 3)
        if detailed:
            # A hull plus local padding fills the sole/palm between landmarks;
            # foreground intersection keeps finger gaps and other real holes.
            outline = np.vstack([anchor, anchor+(points-anchor)*scale])
            span = float(np.ptp(outline, axis=0).max())
            padding = max(torso*(.09 if kind == 'foot' else .025)*scale,
                          span*(.16 if kind == 'foot' else .06), 1.)
            hull = _hull(outline)
            if len(hull) >= 3:
                draw.polygon(hull, fill=255)
            for a, b in zip(hull, hull[1:]+hull[:1]):
                draw.line([a, b], fill=255, width=max(1, round(2*padding)))
            for x, y in outline:
                draw.ellipse((x-padding, y-padding, x+padding, y+padding), fill=255)
            if kind == 'foot':
                # Toe/heel landmarks describe anatomy inside a shoe, not its
                # outer toe box or sole. Preserve local observed context too.
                center = outline.mean(0)
                radius = max(torso*.35*scale,
                             float(np.linalg.norm(outline-anchor,axis=1).max())*.8)
                x, y = center
                draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
            source = 'wholebody_landmarks'
        else:
            delta = anchor-body[parent_index, :2] if _valid(body[parent_index]) else np.array([0., 1.])
            bone = float(np.linalg.norm(delta))
            axis = delta/max(bone, 1e-6) if bone > 1e-6 else np.array([0., 1.])
            # A hand near the hip may touch a skirt. Without finger landmarks,
            # keep its fallback conservative; the independent scale can widen it.
            reach = max(torso*(.4 if kind == 'foot' else .16),
                        bone*(.65 if kind == 'foot' else .4), 4.)*scale
            center = anchor+axis*reach*.2
            # Include any valid partial tip, while retaining a bounded local ROI.
            if len(points):
                reach = max(reach, float(np.linalg.norm(points-center, axis=1).max())*1.12*scale)
            x, y = center
            draw.ellipse((x-reach, y-reach, x+reach, y+reach), fill=255)
            source = 'local_foreground' if foreground is not None else 'pose_envelope'
        region = np.asarray(image, dtype=np.float32)/255
        support = region if foreground is None else np.minimum(region, foreground)
        results.append({'kind': kind, 'side': side, 'source': source,
                        'region': region, 'support': support})
    return results


def extremity_support(regions, shape):
    result = np.zeros(shape, np.float32)
    for region in regions:
        result = np.maximum(result, region['support'])
    return result


def extremity_summary(regions):
    return [{'part': r['side']+'_'+r['kind'], 'source': r['source'],
             'observed_pixels': int(np.count_nonzero(r['support'] > .5))} for r in regions]
