"""从 App 截图中识别 5 个打卡点标记（灰/绿色圆圈 + 白色数字）。"""
import math

import numpy as np
from PIL import Image


def _clusters(ys, xs, min_pix, max_pix):
    pts = set(zip(ys.tolist(), xs.tolist()))
    seen = set()
    out = []
    for p in pts:
        if p in seen:
            continue
        stack = [p]
        seen.add(p)
        comp = []
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (y + dy, x + dx)
                    if q in pts and q not in seen:
                        seen.add(q)
                        stack.append(q)
        if min_pix <= len(comp) <= max_pix:
            cy = sum(c[0] for c in comp) / len(comp)
            cx = sum(c[1] for c in comp) / len(comp)
            yy = [c[0] for c in comp]
            xx = [c[1] for c in comp]
            out.append(dict(cx=cx, cy=cy, n=len(comp),
                            w=max(xx) - min(xx) + 1, h=max(yy) - min(yy) + 1,
                            color=None))
    return out


def _digit_mask(img, cx, cy, scale=1.0):
    w, h = int(round(54 * scale)), int(round(64 * scale))
    x0 = int(round(cx - w / 2))
    y0 = int(round(cy - h / 2))
    crop = img[max(0, y0):y0 + h, max(0, x0):x0 + w]
    if crop.shape[0] < 10 or crop.shape[1] < 10:
        return None
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    m = (lum > 235) & ((mx - mn) < 50)
    ys, xs = np.where(m)
    if len(xs) < 30:
        return None
    cxm, cym = xs.mean(), ys.mean()
    keep = (np.abs(xs - cxm) < 20 * scale) & (np.abs(ys - cym) < 24 * scale)
    xs, ys = xs[keep], ys[keep]
    if len(xs) < 30:
        return None
    x1, x2 = xs.min(), xs.max() + 1
    y1, y2 = ys.min(), ys.max() + 1
    sub = m[y1:y2, x1:x2].astype(np.uint8) * 255
    im = Image.fromarray(sub).resize((28, 36), Image.LANCZOS)
    return np.asarray(im).astype(float) / 255.0


def _ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return 0.0 if d == 0 else float((a * b).sum()) / d


def detect_markers(img_arr, templates, marker_colors, min_score=0.55, verbose=False):
    """img_arr: HxWx3 uint8/float RGB。
    返回 [{'px','py','digit','score','color'}]，按数字排序。"""
    img = img_arr.astype(float)
    H, W = img.shape[:2]
    scale = W / 1080.0
    tol = marker_colors.get("tol", 18)
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]

    results = []
    for key, color in (("gray", marker_colors["gray"]), ("green", marker_colors["green"])):
        cr, cg, cb = color
        m = (np.abs(r - cr) <= tol) & (np.abs(g - cg) <= tol) & (np.abs(b - cb) <= tol)
        ys, xs = np.where(m)
        if len(xs) == 0:
            continue
        clusters = _clusters(ys, xs, int(1500 * scale * scale), int(9000 * scale * scale))
        for c in clusters:
            diam = 70 * scale
            if not (diam * 0.72 <= c["w"] <= diam * 1.35 and diam * 0.72 <= c["h"] <= diam * 1.35):
                continue
            t = _digit_mask(img, c["cx"], c["cy"], scale)
            if t is None:
                continue
            scores = [_ncc(t, tpl) for tpl in templates]
            best = int(np.argmax(scores))
            if scores[best] < min_score:
                if verbose:
                    print(f"[detect] 跳过 {key} ({c['cx']:.0f},{c['cy']:.0f}) 数字置信度 {scores[best]:.2f}")
                continue
            results.append(dict(px=float(c["cx"]), py=float(c["cy"]),
                                digit=best + 1, score=float(scores[best]), color=key))
    results.sort(key=lambda d: d["digit"])
    return results
