"""半自动配准：用户点选 2 个已知地标，拟合 截图像素 -> 底图像素 相似变换。"""
import math

from . import geo


def calibrate(profile, clicks, verbose=True):
    """clicks: [(地标名, (px, py)), ...]（至少 2 个，建议 3 个）。
    返回 dict: transform, scale, rotation_deg, residuals_m"""
    lm = {l["name"]: l for l in profile.landmarks}
    src, dst, used = [], [], []
    for name, (px, py) in clicks:
        if name not in lm:
            raise ValueError(f"未知地标: {name}")
        lon, lat = lm[name]["lon"], lm[name]["lat"]
        mx, my = geo.gcj_to_mosaic_px(lon, lat)
        src.append((float(px), float(py)))
        dst.append((mx, my))
        used.append(name)
    if len(src) < 2:
        raise ValueError("至少需要 2 个地标点")
    s, theta, tx, ty, res = geo.fit_similarity(src, dst)
    resid_m = [r * geo.M_PER_PX for r in res]
    tr = (s, theta, tx, ty)
    if verbose:
        print(f"[calib] 地标 {used}  scale={s:.3f}  rotation={theta:.2f}°  "
              f"残差={[round(r, 1) for r in resid_m]} m")
    if not (0.5 < s < 2.8):
        print(f"[calib] 警告: 缩放异常 ({s:.2f})，请检查点选的地标是否正确")
    if len(resid_m) >= 3 and max(resid_m) > 25:
        print(f"[calib] 警告: 地标残差偏大 ({max(resid_m):.0f} m)，可能点错地标")
    return dict(transform=tr, scale=s, rotation_deg=theta, residuals_m=resid_m, landmarks=used)


def screenshot_px_to_gcj(tr, px, py):
    mx, my = geo.apply_similarity(tr, px, py)
    return geo.mosaic_px_to_gcj(mx, my)


def checkpoints_from_markers(profile, calib, markers):
    """把识别出的打卡点标记像素换算成 GCJ 坐标，返回按顺序的列表。"""
    tr = calib["transform"]
    out = []
    for m in sorted(markers, key=lambda d: d["digit"]):
        lon, lat = screenshot_px_to_gcj(tr, m["px"], m["py"])
        out.append(dict(digit=m["digit"], px=m["px"], py=m["py"],
                        lon=lon, lat=lat, score=m.get("score")))
    return out
