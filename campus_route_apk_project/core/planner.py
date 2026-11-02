"""路线规划：按 1→2→3→4→5 顺序精确经过打卡点，绕校园环路补足到目标里程，
并输出 70~200 个点的稀疏路线（App 路线模拟要求：点数过多会导致步频偏低）。

特性：
- 里程可自动选择：基于校园环路所有组合，算出可规划公里数（0.5 km 步进），
  自动模式默认取 4.0 km；也可手动指定任意 km。
- 5 个打卡点强制写为折线节点（0 m 误差），保证 App 识别。
- 起点可指定（App「起」位置），终点回到起点附近。
- 稀疏化后总点数 70~200（默认 150）。
"""
import math

from . import geo


def _key(p):
    return (round(p[0], 1), round(p[1], 1))


def _append(dst, path):
    if not path:
        return
    if not dst:
        dst.extend(path)
    else:
        dst.extend(path[1:])


def _arc_by_distance(profile, path, step_m):
    if step_m <= 0.5:
        return [path[0], path[-1]] if len(path) > 1 else [path[0]]
    out = [path[0]]
    acc = 0.0
    target = step_m
    for i in range(1, len(path)):
        a, b = path[i - 1], path[i]
        seg = math.hypot(b[0] - a[0], b[1] - a[1]) * profile.m_per_px
        while seg > 0 and acc + seg >= target:
            f = (target - acc) / seg
            out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
            target += step_m
        acc += seg
    if (out[-1][0] - path[-1][0]) ** 2 + (out[-1][1] - path[-1][1]) ** 2 > 1e-18:
        out.append(path[-1])
    return out


def _polyline_wgs(profile, pts):
    return [profile.ds_to_wgs(x, y) for x, y in pts]


def _wgs_len(profile, pts):
    w = _polyline_wgs(profile, pts)
    tot = 0.0
    for i in range(1, len(w)):
        tot += geo.haversine(w[i - 1], w[i])
    return tot


def _find_anchor_indices(dense, anchors_ds):
    n = len(dense)
    idxs = []
    for cp in anchors_ds:
        best_i, best_d = 0, 1e18
        for i in range(n):
            d = (dense[i][0] - cp[0]) ** 2 + (dense[i][1] - cp[1]) ** 2
            if d < best_d:
                best_d, best_i = d, i
        idxs.append(best_i)
    return sorted(set([0] + [i for i in idxs if 0 < i < n - 1] + [n - 1]))


def _resample_by_m(profile, dense, spacing_m, anchors):
    out = [tuple(dense[0])]
    for a, b in zip(anchors[:-1], anchors[1:]):
        sub = dense[a:b + 1]
        seg_len = profile.length_m(sub)
        if seg_len < 1e-6:
            continue
        k = max(1, int(round(seg_len / spacing_m)))
        pts = _arc_by_distance(profile, sub, seg_len / k)
        out.extend(pts[1:])
    return out


def sparsify(profile, dense, anchors_ds, target_points=150, min_points=70, max_points=200):
    """把密集路线抽稀为 ~target_points 个点，并强制包含 anchors_ds 中的点（打卡点/起点）。"""
    if len(dense) < 2:
        return list(dense)
    anchors = _find_anchor_indices(dense, anchors_ds)
    total = profile.length_m(dense)
    spacing = total / max(1.0, (target_points - len(anchors) + 1))
    out = _resample_by_m(profile, dense, spacing, anchors)
    guard = 0
    while len(out) > max_points and guard < 10:
        spacing *= 1.15
        out = _resample_by_m(profile, dense, spacing, anchors)
        guard += 1
    guard = 0
    while len(out) < min_points and guard < 10:
        spacing *= 0.85
        out = _resample_by_m(profile, dense, spacing, anchors)
        guard += 1
    return out


def _available_km(candidate_lengths, tail_len, extra=0.0):
    """根据候选路线长度，给出可规划的公里数（0.5 km 步进，1.0~8.0）。
    尾段最多补 tail_len，必要时用折返最多补 extra。"""
    opts = []
    for i in range(2, 17):
        km = i * 0.5
        t = km * 1000.0
        if any(0 <= t - L <= tail_len + extra for L in candidate_lengths):
            opts.append(km)
    return opts


def plan(profile, checkpoints_gcj, target_m=None, log=print, start_gcj=None,
         target_points=150, min_points=70, max_points=200, auto=False,
         pass_laps=1, pass_radius_m=12.0):
    R = profile.route
    ring = [tuple(p) for p in R["ring"]]

    cps = []
    for i, p in enumerate(checkpoints_gcj, 1):
        ds = profile.gcj_to_ds(*p)
        snap = profile.snap_ds(*ds)
        if snap is None:
            raise ValueError(f"第 {i} 个打卡点距路网太远，无法规划")
        cps.append(snap)
    log(f"[plan] 打卡点已贴合路网: {[(round(x), round(y)) for x, y in cps]}")

    exact_anchors = [profile.gcj_to_ds(*p) for p in checkpoints_gcj]
    start_pt = None
    if start_gcj is not None:
        ds = profile.gcj_to_ds(*start_gcj)
        start_pt = profile.snap_ds(*ds, maxd=120)
        if start_pt is None:
            raise ValueError("起点距路网太远")
        exact_anchors = [ds] + exact_anchors

    def paths_from(src, targets):
        got = profile.segment_paths_from(src, targets)
        return {_key(t): got.get(_key(t)) for t in targets}

    pre_path = None
    if start_pt is not None:
        pre_path = paths_from(start_pt, [cps[0]]).get(_key(cps[0]))
        if pre_path is None:
            raise ValueError("起点到 1 号点路网不连通")

    base_segs = []
    cur = cps[0]
    for nxt in cps[1:]:
        p = paths_from(cur, [nxt]).get(_key(nxt))
        if p is None:
            raise ValueError("打卡点之间路网不连通")
        base_segs.append(p)
        cur = nxt

    from_cp5 = paths_from(cps[-1], ring + [cps[0]])
    p_cp5_to = [from_cp5.get(_key(x)) for x in ring]
    p_stub = from_cp5.get(_key(cps[0]))          # cp5 -> cp1，用于折返补足里程
    if any(p is None for p in p_cp5_to) or p_stub is None:
        raise ValueError("cp5 到环路节点不连通")
    stub_half = profile.length_m(p_stub)

    seg_paths = []
    to_cp1 = []
    for i in range(len(ring) - 1):
        got = paths_from(ring[i], [ring[i + 1], cps[0]])
        seg_paths.append(got.get(_key(ring[i + 1])))
        to_cp1.append(got.get(_key(cps[0])))
    to_cp1.append(paths_from(ring[-1], [cps[0]]).get(_key(cps[0])))
    if any(p is None for p in to_cp1):
        raise ValueError("环路回起点道路不通")
    # 折返路径：cp5 -> cp1 -> ring[0] -> ring[1]（反向复用），用于补足较大缺口
    p_stub = p_stub + list(reversed(to_cp1[0]))[1:]
    if seg_paths:
        p_stub = p_stub + seg_paths[0][1:]
    stub_half = profile.length_m(p_stub)

    if start_pt is not None:
        p_tail = paths_from(cps[0], [start_pt]).get(_key(start_pt))
        if p_tail is not None:
            p_after = paths_from(start_pt, [cps[-1]]).get(_key(cps[-1]))
            if p_after:
                p_tail = p_tail + p_after[1:]
    else:
        p_tail = paths_from(cps[0], [tuple(R["start_node"])]).get(_key(tuple(R["start_node"])))
    if p_tail is None:
        raise ValueError("终点方向道路不通")
    tail_len = profile.length_m(p_tail)

    anchors = ([start_pt] if start_pt else [cps[0]]) + cps

    n = len(ring)
    pref = [0.0] * (n + 1)
    for i in range(n - 1):
        pref[i + 1] = pref[i] + profile.length_m(seg_paths[i])
    base_fixed = profile.length_m(pre_path) if pre_path else 0.0
    for seg in base_segs:
        base_fixed += profile.length_m(seg)
    # 每个打卡点绕小圈（让路线在打卡半径内反复经过）
    loop_extra = 0.0
    if pass_laps and pass_laps > 0 and pass_radius_m > 0:
        loop_extra = len(cps) * (2.0 * pass_radius_m + 2.0 * math.pi * pass_radius_m * pass_laps)
        base_fixed += loop_extra

    def _circle_loop(cp):
        """围绕打卡点的小圈：cp -> 半径 R 的圆（laps 圈）-> cp。"""
        r_ds = pass_radius_m / profile.m_per_px
        n = max(16, int(round(2 * math.pi * pass_laps * r_ds / 1.2)))
        pts = [(cp[0], cp[1])]
        for k in range(1, n + 1):
            ang = 2.0 * math.pi * pass_laps * k / n
            pts.append((cp[0] + r_ds * math.cos(ang), cp[1] + r_ds * math.sin(ang)))
        pts.append((cp[0], cp[1]))
        return pts

    def assemble(i, j, e_off):
        dense = []
        if pre_path:
            _append(dense, pre_path)
        else:
            _append(dense, [cps[0]])
        if pass_laps and pass_laps > 0 and pass_radius_m > 0:
            _append(dense, _circle_loop(cps[0]))
        for idx, p in enumerate(base_segs):
            _append(dense, p)
            if pass_laps and pass_laps > 0 and pass_radius_m > 0 and idx + 1 < len(cps):
                _append(dense, _circle_loop(cps[idx + 1]))
        if pass_laps and pass_laps > 0 and pass_radius_m > 0:
            _append(dense, _circle_loop(cps[-1]))
        _append(dense, p_cp5_to[i])
        for k in range(i, j):
            _append(dense, seg_paths[k])
        _append(dense, to_cp1[j])
        if e_off and e_off > 0:
            tail = profile.partial_m(p_tail, e_off)
            if len(tail) > 1:
                dense.extend(tail[1:])
        return dense

    dlen = {}
    for i in range(n):
        for j in range(i, n):
            dlen[(i, j)] = (base_fixed + profile.length_m(p_cp5_to[i]) +
                            (pref[j] - pref[i]) + profile.length_m(to_cp1[j]))

    def apply_exact(route):
        route = list(route)
        for a in exact_anchors:
            best_i, best_d = 0, 1e18
            for idx, pt in enumerate(route):
                d = (pt[0] - a[0]) ** 2 + (pt[1] - a[1]) ** 2
                if d < best_d:
                    best_d, best_i = d, idx
            route[best_i] = (float(a[0]), float(a[1]))
        return route

    def finish(i, j, target):
        """构建并调里程，返回 (route, L, e, spacing)。"""
        dense0 = assemble(i, j, 0.0)
        sparse0 = sparsify(profile, dense0, anchors, target_points, min_points, max_points)
        L0 = _wgs_len(profile, sparse0)
        spacing_m = L0 / max(1, len(sparse0) - 1)
        e = max(0.0, min(target - L0, tail_len))
        best = None
        for _ in range(40):
            if e > 0.5:
                tail_dense = profile.partial_m(p_tail, e)
                tail_pts = _arc_by_distance(profile, tail_dense, max(4.0, spacing_m))
                if len(tail_pts) < 2:
                    tail_pts = [tail_dense[0], tail_dense[-1]]
                cur = sparse0 + [p for p in tail_pts[1:]]
            else:
                cur = list(sparse0)
            cur = apply_exact(cur)
            L = _wgs_len(profile, cur)
            best = dict(rs=cur, L=L, e=e, spacing=spacing_m)
            if abs(L - target) <= 0.5:
                break
            e += target - L
            if e < 0:
                e = 0.0
            if e > tail_len:
                e = tail_len
                tail_dense = profile.partial_m(p_tail, e)
                tail_pts = _arc_by_distance(profile, tail_dense, max(4.0, spacing_m))
                cur = apply_exact(sparse0 + [p for p in tail_pts[1:]])
                best = dict(rs=cur, L=_wgs_len(profile, cur), e=e, spacing=spacing_m)
                break
        # 尾段用尽仍不够 -> 在 cp5 处沿 cp5->cp1 道路做折返补足
        deficit = target - best["L"]
        if deficit > 1.5:
            idx, bd = 0, 1e18
            for k2, pt in enumerate(best["rs"]):
                d2 = (pt[0] - cps[-1][0]) ** 2 + (pt[1] - cps[-1][1]) ** 2
                if d2 < bd:
                    bd, idx = d2, k2
            route0 = best["rs"]
            d = min(deficit / 2.0, stub_half)
            stub_best = dict(best)
            for _ in range(40):
                stub_dense = profile.partial_m(p_stub, d)
                stub_pts = _arc_by_distance(profile, stub_dense, max(4.0, spacing_m))
                if len(stub_pts) < 2:
                    stub_pts = [stub_dense[0], stub_dense[-1]]
                back = list(reversed(stub_pts))[1:]
                cur = apply_exact(route0[:idx + 1] + stub_pts[1:] + back + route0[idx + 1:])
                L2 = _wgs_len(profile, cur)
                if abs(L2 - target) < abs(stub_best["L"] - target):
                    stub_best = dict(rs=cur, L=L2, e=best["e"], spacing=spacing_m)
                if abs(L2 - target) <= 0.5:
                    stub_best = dict(rs=cur, L=L2, e=best["e"], spacing=spacing_m)
                    break
                d += (target - L2) / 2.0
                if d < 0:
                    d = 0.0
                if d > stub_half:
                    d = stub_half
                    break
            best = stub_best
        return best

    # ---- 用一条参考路线校准"密集长度 -> 稀疏长度"的比例 ----
    ref_key = max(dlen, key=lambda k: dlen[k])
    ref_dense = assemble(ref_key[0], ref_key[1], 0.0)
    ref_sparse = sparsify(profile, ref_dense, anchors, target_points, min_points, max_points)
    L_ref = _wgs_len(profile, ref_sparse)
    ratio = max(0.5, min(1.05, L_ref / max(1.0, dlen[ref_key])))
    available_km = _available_km([v * ratio for v in dlen.values()], tail_len, extra=2.0 * stub_half)

    est = {k: v * ratio for k, v in dlen.items()}
    if auto:
        if 4.0 in available_km:
            target = 4000.0
        elif available_km:
            target = min(available_km, key=lambda km: abs(km - 4.0)) * 1000.0
        else:
            target = max(est.values()) + tail_len * 0.5
        log(f"[plan] 自动选择里程 {target/1000:.1f} km")
    else:
        target = float(target_m or R["target_m"])

    # ---- 选绕行组合：优先"稀疏估算略小于目标、可用尾段补齐" ----
    cand = [k for k in dlen if 0 <= target - est[k] <= tail_len + 2.0 * stub_half]
    cand.sort(key=lambda k: abs(target - est[k] - tail_len * 0.45))
    if not cand:
        cand = sorted(dlen, key=lambda k: abs(est[k] - target))
    chosen = None
    for k in cand[:8]:
        r = finish(k[0], k[1], target)
        if chosen is None or abs(r["L"] - target) < abs(chosen["L"] - target):
            chosen = dict(i=k[0], j=k[1], **r)
        if abs(r["L"] - target) <= 0.8:
            break
    if chosen is None:
        raise RuntimeError("没有可用的绕行方案")

    route = chosen["rs"]
    wgs = _polyline_wgs(profile, route)
    cp_pass = []
    for c in cps:
        cp_pass.append(round(min(math.hypot(c[0] - x, c[1] - y) for x, y in route) * profile.m_per_px, 2))
    lons = [p[0] for p in wgs]
    lats = [p[1] for p in wgs]
    if abs(chosen["L"] - target) > 2:
        log(f"[plan] 警告: 目标 {target/1000:.1f} km 无法精确达到，已生成 {chosen['L']/1000:.2f} km"
            f"（可规划: {', '.join(f'{k:g}' for k in available_km) if available_km else '无'} km）")
    log(f"[plan] 采用绕行组合 ring[{chosen['i']}..{chosen['j']}]")
    log(f"[route] 最终 {chosen['L']:.1f} m / {len(route)} 点（要求 {min_points}~{max_points} 点）")
    return dict(route_ds=route,
                route_dense_ds=assemble(chosen["i"], chosen["j"], chosen["e"]),
                route_wgs=wgs, length_m=chosen["L"], target_m=target,
                point_count=len(route), checkpoints=cps, checkpoint_pass_m=cp_pass,
                ring_variant=(chosen["i"], chosen["j"]), end_offset_m=chosen["e"],
                start_offset_m=0.0, available_km=available_km, auto=bool(auto),
                bbox_wgs=[min(lons), min(lats), max(lons), max(lats)],
                start_wgs=wgs[0], end_wgs=wgs[-1])
