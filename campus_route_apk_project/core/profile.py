"""校区档案、路网栅格图、最短路径与几何工具。"""
import json
import math
import os
import heapq

import numpy as np
from PIL import Image

from . import geo

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dilate(mask):
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


class Profile:
    """校区档案：路网掩膜 + 地标 + 路线参数。"""

    def __init__(self, path=None):
        self.path = os.path.abspath(path or os.path.join(TOOL_DIR, "campus_profile.json"))
        with open(self.path, encoding="utf-8") as f:
            self.data = json.load(f)
        base = os.path.dirname(self.path)
        self.base = base

        m = self.data["mask"]
        self.mask = np.asarray(Image.open(os.path.join(base, m["file"])).convert("L")) > 128
        self.mask = _dilate(self.mask)
        self.H, self.W = self.mask.shape
        self.m_per_px = float(m["m_per_px"])

        self.templates = []
        for rel in self.data["digits"]:
            im = Image.open(os.path.join(base, rel)).convert("L").resize((28, 36), Image.LANCZOS)
            self.templates.append(np.asarray(im).astype(float) / 255.0)

        self.route = self.data["route"]
        self.marker_colors = self.data["marker_colors"]
        self.landmarks = self.data["landmarks"]

    # ---------- 坐标 ----------
    def ds_to_mosaic(self, x, y):
        return x * 2.0, y * 2.0

    def mosaic_to_ds(self, x, y):
        return x / 2.0, y / 2.0

    def gcj_to_ds(self, lon, lat):
        return self.mosaic_to_ds(*geo.gcj_to_mosaic_px(lon, lat))

    def ds_to_gcj(self, x, y):
        return geo.mosaic_px_to_gcj(*self.ds_to_mosaic(x, y))

    def ds_to_wgs(self, x, y):
        return geo.gcj2wgs(*self.ds_to_gcj(x, y))

    def length_m(self, pts):
        """ds 像素折线长度（米，按 profile 比例）。"""
        tot = 0.0
        for i in range(1, len(pts)):
            tot += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        return tot * self.m_per_px

    # ---------- 路网 ----------
    def snap_ds(self, x, y, maxd=80):
        xi, yi = int(round(x)), int(round(y))
        if 0 <= yi < self.H and 0 <= xi < self.W and self.mask[yi, xi]:
            return (float(xi), float(yi))
        for r in range(2, maxd, 2):
            y0, y1 = max(0, yi - r), min(self.H, yi + r + 1)
            x0, x1 = max(0, xi - r), min(self.W, xi + r + 1)
            sub = self.mask[y0:y1, x0:x1]
            if sub.any():
                ys, xs = np.where(sub)
                d2 = (ys + y0 - y) ** 2 + (xs + x0 - x) ** 2
                i = int(np.argmin(d2))
                if math.sqrt(d2[i]) <= maxd:
                    return (float(x0 + xs[i]), float(y0 + ys[i]))
        return None

    def dijkstra(self, src):
        """单源最短路（8 邻域）。返回 (dist, prev)，prev 为 (H,W,2) 的 int32。"""
        H, W = self.H, self.W
        sy, sx = int(round(src[1])), int(round(src[0]))
        if not (0 <= sy < H and 0 <= sx < W and self.mask[sy, sx]):
            raise ValueError("起点不在路网上")
        c1 = self.m_per_px
        c2 = c1 * math.sqrt(2)
        nb = [(-1, -1, c2), (-1, 0, c1), (-1, 1, c2), (0, -1, c1),
              (0, 1, c1), (1, -1, c2), (1, 0, c1), (1, 1, c2)]
        dist = np.full((H, W), np.inf, np.float32)
        prev = np.full((H, W, 2), -1, np.int32)
        dist[sy, sx] = 0.0
        pq = [(0.0, sy, sx)]
        mask = self.mask
        while pq:
            d, y, x = heapq.heappop(pq)
            if d > dist[y, x]:
                continue
            for dy, dx, c in nb:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and mask[yy, xx]:
                    nd = d + c
                    if nd < dist[yy, xx] - 1e-9:
                        dist[yy, xx] = nd
                        prev[yy, xx] = (y, x)
                        heapq.heappush(pq, (nd, yy, xx))
        return dist, prev

    @staticmethod
    def _trace(prev, src, dst):
        path = []
        cy, cx = int(round(dst[1])), int(round(dst[0]))
        sy, sx = int(round(src[1])), int(round(src[0]))
        guard = 0
        while (cy, cx) != (sy, sx):
            path.append((float(cx), float(cy)))
            p = prev[cy, cx]
            if p[0] < 0:
                return None
            cy, cx = int(p[0]), int(p[1])
            guard += 1
            if guard > 4_000_000:
                return None
        path.append((float(sx), float(sy)))
        path.reverse()
        return path

    def segment(self, a, b):
        """a->b 的路网路径与长度。返回 (path_ds, length_m)。"""
        dist, prev = self.dijkstra(a)
        by, bx = int(round(b[1])), int(round(b[0]))
        if not np.isfinite(dist[by, bx]):
            raise ValueError("两点之间路网不连通")
        return self._trace(prev, a, b), float(dist[by, bx])

    def segment_paths_from(self, src, targets):
        """一次 Dijkstra，返回 src 到多个目标点的路径字典 {(x,y): path}。"""
        dist, prev = self.dijkstra(src)
        out = {}
        for t in targets:
            ty, tx = int(round(t[1])), int(round(t[0]))
            if np.isfinite(dist[ty, tx]):
                out[(round(t[0], 1), round(t[1], 1))] = self._trace(prev, src, t)
        return out

    # ---------- 折线工具 ----------
    @staticmethod
    def partial(path, meters):
        """沿路径走 meters 米（以路径点坐标换算），返回子路径（含起点，不含终点后内容）。"""
        return Profile._along(path, meters, include_next=True)

    @staticmethod
    def _along(path, meters, include_next=False):
        if meters <= 0:
            return [path[0]]
        acc = 0.0
        for i in range(1, len(path)):
            step = math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
            if acc + step >= meters / 1.0:  # ds px -> meters handled by caller scale
                f = (meters - acc) / step if step else 0.0
                pt = (path[i - 1][0] + f * (path[i][0] - path[i - 1][0]),
                      path[i - 1][1] + f * (path[i][1] - path[i - 1][1]))
                if include_next:
                    return path[:i] + [pt]
                return pt
            acc += step
        return path[-1] if not include_next else path[:]

    def along_m(self, path, meters):
        """沿 ds 路径走 meters 米，返回点 (ds)。"""
        need = meters / self.m_per_px
        return self._along(path, need, include_next=False)

    def partial_m(self, path, meters):
        need = meters / self.m_per_px
        return self._along(path, need, include_next=True)
