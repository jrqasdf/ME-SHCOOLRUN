"""导出与样例完全一致的 .route.json（多坐标：BD-09 / WGS-84），以及路线预览图。"""
import json
import math
import os
import time

from PIL import Image, ImageDraw, ImageFont

from . import geo

ALTITUDE = 55  # 与样例一致（App 只做展示/回放，不使用海拔）


def build_route_dict(route_wgs, name=None, created_ms=None):
    now = time.time()
    if created_ms is None:
        created_ms = int(now * 1000)
    if not name:
        name = "route_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(created_ms / 1000))
    pts = []
    for lon, lat in route_wgs:
        glon, glat = geo.wgs2gcj(lon, lat)
        blon, blat = geo.gcj2bd(glon, glat)
        pts.append(dict(bdLongitude=round(blon, 13), bdLatitude=round(blat, 13),
                        wgsLongitude=round(lon, 13), wgsLatitude=round(lat, 13),
                        altitude=ALTITUDE))
    return dict(version=1, name=name, createdAt=created_ms,
                updatedAt=created_ms + 12000, points=pts)


def route_length_wgs(route_dict):
    pts = [(p["wgsLongitude"], p["wgsLatitude"]) for p in route_dict["points"]]
    tot = 0.0
    for i in range(1, len(pts)):
        tot += geo.haversine(pts[i - 1], pts[i])
    return tot


def save_route(route_dict, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(route_dict, f, ensure_ascii=False)
    return out_path


def _font(size):
    for name in ("C:/Windows/Fonts/msyh.ttc", "/system/fonts/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_preview(profile, route_ds, checkpoints_ds, out_path, title=None,
                   start_pt=None, end_pt=None, basemap="vector"):
    """route_ds/checkpoints_ds 为路网坐标（mask 像素）。
    basemap: "vector"=高德矢量地图（默认），"sat"=高德卫星图。"""
    sat = (profile.data.get("satellite") or {}).get("file")
    base_file = sat if (basemap == "sat" and sat) else profile.data["basemap"]["file"]
    base = Image.open(os.path.join(profile.base, base_file)).convert("RGB")
    img = base.resize((profile.W, profile.H), Image.LANCZOS) if base.size != (profile.W, profile.H) else base.copy()
    dr = ImageDraw.Draw(img)
    dr.line([(x, y) for x, y in route_ds], fill=(230, 30, 30), width=4, joint="curve")
    f1 = _font(26)
    f2 = _font(20)
    for i, (x, y) in enumerate(checkpoints_ds, 1):
        dr.ellipse([x - 14, y - 14, x + 14, y + 14], fill=(255, 255, 255),
                   outline=(0, 90, 220), width=4)
        dr.text((x - 8, y - 14), str(i), fill=(0, 90, 220), font=f1)
        dr.text((x + 18, y - 15), f"CP{i}", fill=(0, 90, 220), font=f2)
    if start_pt:
        dr.ellipse([start_pt[0] - 9, start_pt[1] - 9, start_pt[0] + 9, start_pt[1] + 9], fill=(0, 160, 80))
        dr.text((start_pt[0] + 11, start_pt[1] - 24), "起点", fill=(0, 140, 60), font=f2)
    if end_pt:
        dr.polygon([(end_pt[0], end_pt[1] - 11), (end_pt[0] + 10, end_pt[1] + 7),
                    (end_pt[0] - 10, end_pt[1] + 7)], fill=(230, 120, 0))
        dr.text((end_pt[0] + 12, end_pt[1] + 2), "终点", fill=(200, 100, 0), font=f2)
    if title:
        dr.rectangle([14, 14, 14 + 560, 14 + 66], fill=(255, 255, 255))
        dr.text((24, 20), title, fill=(0, 0, 0), font=f2)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    img.save(out_path)
    return out_path
