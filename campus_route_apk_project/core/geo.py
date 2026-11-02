"""坐标系工具：高德 GCJ-02 <-> 底图像素 <-> WGS-84 / BD-09，以及相似变换拟合。"""
import math

MOSAIC_X0 = 211440
MOSAIC_Y0 = 112030
MOSAIC_Z = 18
MOSAIC_N = 2 ** MOSAIC_Z * 256.0          # 该 zoom 下全球像素宽
M_PER_PX = 0.5401                         # 底图像素对应的地面米数（约）

_PI = math.pi
_A = 6378245.0
_EE = 0.00669342162296594323


def mosaic_px_to_gcj(x, y):
    gx = MOSAIC_X0 * 256 + x
    gy = MOSAIC_Y0 * 256 + y
    lon = gx / MOSAIC_N * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(_PI * (1 - 2 * gy / MOSAIC_N))))
    return lon, lat


def gcj_to_mosaic_px(lon, lat):
    gx = (lon + 180.0) / 360.0 * MOSAIC_N
    n = _PI - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))
    gy = n * MOSAIC_N / (2 * _PI)
    return gx - MOSAIC_X0 * 256, gy - MOSAIC_Y0 * 256


# ---------- GCJ-02 <-> WGS-84 ----------
def _out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _tlat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _tlng(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def wgs2gcj(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _tlat(lng - 105.0, lat - 35.0)
    dlng = _tlng(lng - 105.0, lat - 35.0)
    rad = lat / 180.0 * _PI
    magic = math.sin(rad)
    magic = 1 - _EE * magic * magic
    sm = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sm) * _PI)
    dlng = (dlng * 180.0) / (_A / sm * math.cos(rad) * _PI)
    return lng + dlng, lat + dlat


def gcj2wgs(lng, lat):
    wlng, wlat = lng, lat
    for _ in range(30):
        glng, glat = wgs2gcj(wlng, wlat)
        wlng += lng - glng
        wlat += lat - glat
    return wlng, wlat


def gcj2bd(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat *_PI * 3000.0 / 180.0)
    th = math.atan2(lat, lng) + 0.000003 * math.cos(lng * _PI * 3000.0 / 180.0)
    return z * math.cos(th) + 0.0065, z * math.sin(th) + 0.006


# ---------- 距离 / 相似变换 ----------
def haversine(p, q):
    """经纬度点对距离（米）"""
    lon1, lat1 = p
    lon2, lat2 = q
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    return 2 * R * math.asin(math.sqrt(math.sin(dp / 2) ** 2 +
                                       math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def fit_similarity(src, dst):
    """最小二乘拟合 dst = s*R(theta)*src + t（屏幕像素 -> 底图像素）。
    src/dst: [(x, y), ...]，至少 2 对。返回 (s, theta_deg, tx, ty, residuals)。"""
    if len(src) < 2:
        raise ValueError("至少需要 2 个对应点")
    sx = sum(p[0] for p in src) / len(src)
    sy = sum(p[1] for p in src) / len(src)
    dx = sum(p[0] for p in dst) / len(dst)
    dy = sum(p[1] for p in dst) / len(dst)
    zs = [complex(p[0] - sx, p[1] - sy) for p in src]
    zd = [complex(p[0] - dx, p[1] - dy) for p in dst]
    num = sum(d * s.conjugate() for d, s in zip(zd, zs))
    den = sum(abs(s) ** 2 for s in zs)
    a = num / den
    s = abs(a)
    theta = math.degrees(math.atan2(a.imag, a.real))
    tx = dx - (a.real * sx - a.imag * sy)
    ty = dy - (a.imag * sx + a.real * sy)
    res = []
    for (x, y), (ex, ey) in zip(src, dst):
        px = a.real * x - a.imag * y + tx
        py = a.imag * x + a.real * y + ty
        res.append(math.hypot(px - ex, py - ey))
    return s, theta, tx, ty, res


def apply_similarity(tr, x, y):
    s, theta, tx, ty = tr[0], tr[1], tr[2], tr[3]
    c = math.cos(math.radians(theta))
    sn = math.sin(math.radians(theta))
    return (s * (c * x - sn * y) + tx, s * (sn * x + c * y) + ty)
