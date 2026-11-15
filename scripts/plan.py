import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moc3 import Moc3

"""
plan.py —— 给任意 VT / Live2D 模型**自动**生成去水印方案。

不依赖具体的网格索引，按下面的优先级自动判定，输出一份可执行的 plan：
    {"moc3": "...", "meshes": [..], "erase_tex": [...], "why": "..."}

判定顺序（命中即停，全部给证据）：
  1. 部件名命中     cdi3 Parts[].Name 含 水印/声明/作者/logo  → 取该部件下所有网格
  2. 参数驱动      cdi3 Parameters[].Name 含 水印，且该参数能推出"极值处不透明度归零"的网格
  3. 孤儿全屏网格  parentPart=-1 且（无变形器 或 位置跨度 > 半个画布）
  4. 文字几何      UV 连通块数明显高于全模型中位数（≥3 且是中位数的 2 倍以上）
  5. 贴图印章      以上都没有 → 交给 scan_texture.py 人工确认

用法：
    python3 plan.py <模型目录或moc3> [--json plan.json]
"""

SUSPECT = ('水印', '声明', '作者', '禁止', '转载', 'logo', 'Logo', '署名')


def load_cdi(moc_path):
    p = os.path.splitext(moc_path)[0] + '.cdi3.json'
    if not os.path.exists(p):
        return {}, {}
    try:
        d = json.load(open(p, encoding='utf-8'))
    except Exception:
        return {}, {}
    pn = {x.get('Id'): x.get('Name', '') for x in d.get('Parameters', [])}
    pt = {x.get('Id'): x.get('Name', '') for x in d.get('Parts', [])}
    return pn, pt


def uv_box(m, i):
    import numpy as np
    T = m.T
    n = m.s32(T[43], i)
    if n < 3:
        return None
    b0 = m.s32(T[44], i)
    U = np.frombuffer(m.b, dtype='<f4', count=2 * n, offset=T[78] + 4 * b0).reshape(n, 2)
    return tuple(round(float(v), 3) for v in (U[:, 0].min(), U[:, 1].min(), U[:, 0].max(), U[:, 1].max()))


def connectivity(m, i, S=96):
    """UV 三角形栅格化后的连通块数量（文字会碎成很多块）"""
    try:
        import numpy as np
        from scipy import ndimage as ndi
    except Exception:
        return None
    T = m.T
    n = m.s32(T[43], i); c = m.s32(T[46], i)
    if n < 3 or c < 3:
        return 0
    b0 = m.s32(T[44], i); ib = m.s32(T[45], i)
    U = np.frombuffer(m.b, dtype='<f4', count=2*n, offset=T[78] + 4*b0).reshape(n, 2).astype(float)
    idx = np.frombuffer(m.b, dtype='<i2', count=c, offset=T[79] + ib*2).reshape(-1, 3).astype('int32')
    mask = np.zeros((S, S), bool)
    for tri in idx:
        if tri.max() >= n:
            continue
        pts = U[tri] * (S - 1)
        x0 = int(max(0, pts[:, 0].min())); x1 = int(min(S - 1, np.ceil(pts[:, 0].max())))
        y0 = int(max(0, pts[:, 1].min())); y1 = int(min(S - 1, np.ceil(pts[:, 1].max())))
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1+1) + .5, np.arange(y0, y1+1) + .5)
        d = (pts[1, 1]-pts[2, 1])*(pts[0, 0]-pts[2, 0]) + (pts[2, 0]-pts[1, 0])*(pts[0, 1]-pts[2, 1])
        if abs(d) < 1e-9:
            continue
        a = ((pts[1, 1]-pts[2, 1])*(X-pts[2, 0]) + (pts[2, 0]-pts[1, 0])*(Y-pts[2, 1]))/d
        b = ((pts[2, 1]-pts[0, 1])*(X-pts[2, 0]) + (pts[0, 0]-pts[2, 0])*(Y-pts[2, 1]))/d
        cc = 1 - a - b
        mask[y0:y1+1, x0:x1+1] |= ((a >= 0) & (b >= 0) & (cc >= 0))
    if not mask.any():
        return 0
    lab, _ = ndi.label(mask)
    sizes = np.bincount(lab.ravel())[1:]
    return int((sizes >= 3).sum())


def has_geom(m, i):
    """还有没有可画的几何：去过水印的网格 indexCount 已被清零，必须排除，否则会把普通效果误判成水印"""
    T = m.T
    n = m.s32(T[43], i); ic = m.s32(T[46], i)
    if n < 3 or ic < 3:
        return False
    try:
        import numpy as np
    except Exception:
        return True
    b0 = m.s32(T[44], i)
    U = np.frombuffer(m.b, dtype='<f4', count=2 * min(n, 8), offset=T[78] + 4 * b0)
    return bool(U.any())


def pos_span(m, i):
    """网格在模型空间的跨度（用来找全屏网格；不同模型坐标系不同，只看相对大小）"""
    try:
        import numpy as np
    except Exception:
        return None
    T = m.T
    n = m.s32(T[43], i)
    if n < 3:
        return None
    kf = m.s32(T[34], i)
    if kf < 0:
        return None
    pb = m.s32(T[70], kf)
    P = np.frombuffer(m.b, dtype='<f4', count=2*n, offset=T[71] + 4*pb).reshape(n, 2)
    import numpy as np
    return float(max(np.ptp(P[:, 0]), np.ptp(P[:, 1])))


def build_plan(moc_path):
    m = Moc3(moc_path)
    pn, pt = load_cdi(moc_path)
    ids = m.ids(m.artIds, m.nArt)
    pids = m.ids(m.partIds, m.nParts)
    T = m.T
    plan = {'moc3': moc_path, 'meshes': [], 'erase_tex': [], 'why': []}

    # 1. 部件名
    for i, pid in enumerate(pids):
        if any(k in (pid + pt.get(pid, '')) for k in SUSPECT):
            kids = [j for j in range(m.nArt) if m.s32(T[39], j) == i and has_geom(m, j)]
            if kids:
                plan['meshes'] = kids
                plan['why'].append('部件 #%d「%s / %s」下挂 %d 个网格' % (i, pid, pt.get(pid, ''), len(kids)))
                return plan

    # 2. 参数驱动：既"一头不透明度为 0"，又满足可疑特征（孤儿 / 全屏 / 文字几何）
    sus_params = [i for i, pid in enumerate(m.ids(m.paramIds, m.nParam))
                  if any(k in (pid + pn.get(pid, '')) for k in SUSPECT)]
    if sus_params:
        dip = []
        for j in range(m.nArt):
            kf = m.s32(T[34], j)
            if kf < 0 or not has_geom(m, j):
                continue
            begin = m.s32(T[35], j); cnt = m.s32(T[36], j)
            ops = [m.f32(T[68], begin + k) for k in range(cnt)]
            if len(ops) >= 2 and (min(ops) <= 0.05 < max(ops)):
                dip.append(j)
        # 用"关键键值分组"锁定水印家族：把连通块最多的那个当种子，取与它键值集合相同的网格
        def keys_of(j):
            kf = m.s32(T[34], j)
            ks = []
            for bd in m.keyform_bindings(kf):
                ks += [round(k, 4) for k in m.binding_keys(bd)]
            return tuple(sorted(set(ks)))

        cc = {j: connectivity(m, j) for j in dip}
        cc = {j: c for j, c in cc.items() if c is not None}
        pick = []
        if cc:
            seed = max(cc, key=lambda j: cc[j])
            K = keys_of(seed)
            family = [j for j in dip if keys_of(j) == K]
            # 孪生：同 UV、同键值、孤儿（例如一直全透明的遮盖片）
            boxes = {uv_box(m, j) for j in family if uv_box(m, j)}
            for j in range(m.nArt):
                if j in family or m.s32(T[39], j) != -1 or m.s32(T[34], j) < 0:
                    continue
                if not has_geom(m, j):
                    continue
                if keys_of(j) == K and uv_box(m, j) in boxes:
                    family.append(j)
            all_orphan = all(m.s32(T[39], j) == -1 for j in family)
            has_orphan = any(m.s32(T[39], j) == -1 for j in family)
            # 可信度门槛：种子像文字(>=3块)且家族里有孤儿，或整组都是孤儿
            if (cc[seed] >= 3 and has_orphan) or (all_orphan and family):
                pick = family
                plan['why'].append('以键值集合 %s、连通块最多的 #%d（%d 块）为种子，锁定同族 %d 个网格'
                                   % (list(K), seed, cc[seed], len(family)))
        # 补上"同 UV、同键值、同为孤儿"的孪生网格（例如遮盖面片，它们本身可能一直透明）
        if pick:
            def uvb(j):
                n = m.s32(T[43], j)
                if n < 3:
                    return None
                b0 = m.s32(T[44], j)
                try:
                    import numpy as np
                    U = np.frombuffer(m.b, dtype='<f4', count=2*n, offset=T[78]+4*b0).reshape(n, 2)
                    return tuple(round(float(v), 3) for v in (U[:, 0].min(), U[:, 1].min(), U[:, 0].max(), U[:, 1].max()))
                except Exception:
                    return None
            boxes = {uvb(j) for j in pick if uvb(j)}
            K = keys_of(pick[0])
            extra = [j for j in range(m.nArt)
                     if j not in pick and m.s32(T[39], j) == -1
                     and m.s32(T[34], j) >= 0 and keys_of(j) == K and uvb(j) in boxes]
            if extra:
                pick = sorted(pick + extra)
                plan['why'].append('并补入 %d 个同 UV、同键值的孪生网格：%s'
                                   % (len(extra), [ids[j] for j in extra]))
        if not pick:                              # 退路：孤儿优先
            orphan = [j for j in dip if m.s32(T[39], j) == -1]
            pick = orphan
        if pick:
            plan['meshes'] = sorted(pick)
            plan['why'].append('参数 %s 命名的水印参数 + 只取其中"孤儿网格/文字几何"的 %d 个：%s'
                               % ([m.ids(m.paramIds, m.nParam)[i] for i in sus_params],
                                  len(pick), [ids[j] for j in pick][:8]))
            if len(dip) > len(pick):
                plan['why'].append('（另有 %d 个网格也会在极值处淡出，但属于正常部件，已排除：%s）'
                                   % (len(dip)-len(pick), [ids[j] for j in dip if j not in pick][:10]))
            return plan

    # 3. 孤儿全屏网格
    # 孤儿全屏网格：必须连变形器都没挂（parentDef = -1），否则只是普通美术
    spans = {j: pos_span(m, j) for j in range(m.nArt)
             if m.s32(T[39], j) == -1 and m.s32(T[40], j) == -1 and has_geom(m, j)}
    spans = {k: v for k, v in spans.items() if v}
    if spans:
        mx = max(spans.values())
        cand = [j for j, v in spans.items() if v >= mx * 0.5]
        if cand:
            plan['meshes'] = sorted(cand)
            plan['why'].append('parentPart=-1 的孤儿网格中，跨度接近最大值的 %d 个：%s'
                               % (len(cand), [ids[j] for j in cand][:8]))
            return plan

    # 4. 文字几何：连通块数明显高于中位数
    cc = [(j, connectivity(m, j)) for j in range(m.nArt) if m.s32(T[43], j) >= 30]
    cc = [(j, c) for j, c in cc if c is not None]
    if cc:
        vals = sorted(c for _, c in cc)
        med = vals[len(vals)//2]
        cand = [j for j, c in cc if c >= max(6, med*2)]
        if cand:
            plan['meshes'] = sorted(cand)
            plan['why'].append('UV 连通块数远高于全模型中位数（中位数 %d），判定为文字几何：%s'
                               % (med, [ids[j] for j in cand][:8]))
            return plan

    # 名字像水印、但几何都空了 → 这份模型已经去过水印
    wm_parts = [p for p in pids if any(k in (p + pt.get(p, '')) for k in SUSPECT)]
    wm_params = [p for p in m.ids(m.paramIds, m.nParam)
                 if any(k in (p + pn.get(p, '')) for k in SUSPECT)]
    if wm_parts or wm_params:
        left = []
        for j in range(m.nArt):
            pp = m.s32(T[39], j)
            if pp >= 0 and pids[pp] in wm_parts and has_geom(m, j):
                left.append(j)
        if not left:
            plan['why'].append('存在水印相关的部件/参数（%s），但几何已被移除——这份模型已经去过水印'
                               % '/'.join(list(wm_parts) + list(wm_params)))
            plan['already_clean'] = True
            return plan
    plan['why'].append('没找到几何形态的水印；请用 scan_texture.py 扫贴图，或人工指定 --ids/--meshes')
    return plan


def main(target, out=None):
    moc = target if target.endswith('.moc3') else None
    if not moc:
        for dp, dns, fns in os.walk(target):
            for f in fns:
                if f.endswith('.moc3'):
                    moc = os.path.join(dp, f); break
            if moc:
                break
    assert moc, '找不到 .moc3'
    plan = build_plan(moc)
    txt = json.dumps(plan, ensure_ascii=False, indent=1)
    print(txt)
    if out:
        open(out, 'w', encoding='utf-8').write(txt)
        print('\n已写入', out)
    return plan


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    out = None
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
    main(sys.argv[1], out)
