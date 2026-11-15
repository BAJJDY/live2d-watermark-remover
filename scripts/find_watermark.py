import sys, os, json, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moc3 import Moc3

"""
find_watermark.py —— 在 Live2D 的 .moc3 里找出"水印"到底挂在哪。

用法:
    python3 find_watermark.py <moc3路径> [cdi3路径]

输出分四类线索，任何一条命中都可能是水印入口：
  A 参数名：cdi3.json 里 Parameters[].Name 含 水印/声明/作者/禁止/转载
  B 部件名：cdi3.json 里 Parts[].Name 含 水印/声明/作者/logo
  C 孤儿网格：parentPart = -1（不属于任何部件，常见于追加的水印）
  D 文字几何：UV 空间连通域很多（汉字的轮廓被拆成三角形，会碎成很多块）
同时打印每个候选的 贴图号 / 顶点数 / 三角形数 / 透明度关键帧 / 关键键值。
"""

def load_cdi(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}, {}
    pn = {x.get('Id'): x.get('Name', '') for x in d.get('Parameters', [])}
    pt = {x.get('Id'): x.get('Name', '') for x in d.get('Parts', [])}
    return pn, pt


def connectivity(m, i, S=128):
    """把网格的 UV 三角形栅格化，数连通块：文字会碎成很多块，普通美术一般 1~3 块"""
    import numpy as np
    from scipy import ndimage as ndi
    T = m.T
    n = m.s32(T[43], i); c = m.s32(T[46], i)
    if n < 3 or c < 3:
        return 0, 0.0
    b0 = m.s32(T[44], i); ib = m.s32(T[45], i)
    U = np.frombuffer(m.b, dtype='<f4', count=2*n, offset=T[78]+4*b0).reshape(n, 2).astype(np.float64)
    idx = np.frombuffer(m.b, dtype='<i2', count=c, offset=T[79]+ib*2).reshape(-1, 3).astype(np.int32)
    mask = np.zeros((S, S), bool)
    for tri in idx:
        if tri.max() >= n:
            continue
        pts = U[tri]*(S-1)
        x0 = int(max(0, pts[:,0].min())); x1 = int(min(S-1, np.ceil(pts[:,0].max())))
        y0 = int(max(0, pts[:,1].min())); y1 = int(min(S-1, np.ceil(pts[:,1].max())))
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1+1)+.5, np.arange(y0, y1+1)+.5)
        d = (pts[1,1]-pts[2,1])*(pts[0,0]-pts[2,0]) + (pts[2,0]-pts[1,0])*(pts[0,1]-pts[2,1])
        if abs(d) < 1e-9:
            continue
        a = ((pts[1,1]-pts[2,1])*(X-pts[2,0]) + (pts[2,0]-pts[1,0])*(Y-pts[2,1]))/d
        b = ((pts[2,1]-pts[0,1])*(X-pts[2,0]) + (pts[0,0]-pts[2,0])*(Y-pts[2,1]))/d
        cc = 1-a-b
        mask[y0:y1+1, x0:x1+1] |= ((a >= 0) & (b >= 0) & (cc >= 0))
    if not mask.any():
        return 0, 0.0
    lab, ncomp = ndi.label(mask)
    sizes = np.bincount(lab.ravel())[1:]
    return int((sizes >= 3).sum()), float(mask.mean())


def main(moc_path, cdi_path=None):
    m = Moc3(moc_path); T = m.T
    if cdi_path is None:
        cdi_path = os.path.splitext(moc_path)[0] + '.cdi3.json'
    pn, pt = load_cdi(cdi_path)
    ids = m.ids(m.artIds, m.nArt)
    pids = m.ids(m.partIds, m.nParts)
    print("模型：%s  网格 %d / 参数 %d / 部件 %d / 变形器 %d" % (os.path.basename(moc_path), m.nArt, m.nParam, m.nParts, m.nDef))

    print("\n== A. 参数名线索 ==")
    hitparams = []
    for i, pid in enumerate(m.ids(m.paramIds, m.nParam)):
        nm = pn.get(pid, '')
        if any(k in (pid + nm) for k in ('水印', '声明', '作者', '禁止', '转载', 'logo', 'Logo')):
            rng = (m.f32(T[52], i), m.f32(T[51], i), m.f32(T[53], i))
            print("  param #%d  %s / %s   min/max/default=%s" % (i, pid, nm, rng))
            hitparams.append((i, pid, nm))
    if not hitparams:
        print("  （无）")

    print("\n== B. 部件名线索 ==")
    hitparts = set()
    for i, pid in enumerate(pids):
        nm = pt.get(pid, '')
        if any(k in (pid + nm) for k in ('水印', '声明', '作者', 'logo', 'Logo')):
            kids = [j for j in range(m.nArt) if m.s32(T[39], j) == i]
            print("  部件 #%d  %s / %s  下挂网格 %s" % (i, pid, nm, kids))
            hitparts.add(i)
    if not hitparts:
        print("  （无）")

    print("\n== C. 孤儿网格（parentPart = -1）==")
    orph = [j for j in range(m.nArt) if m.s32(T[43], j) > 0 and m.s32(T[39], j) == -1]
    for j in orph:
        print("  #%d %s tex=%d vtx=%d tris=%d parentDef=%d" %
              (j, ids[j], m.s32(T[41], j), m.s32(T[43], j), m.s32(T[46], j)//3, m.s32(T[40], j)))
    if not orph:
        print("  （无）")

    print("\n== D. 文字几何（UV 连通块多）==")
    cand = []
    try:
        import numpy, scipy  # noqa
    except Exception:
        print("  需要 numpy + scipy：pip install numpy scipy")
        cand = []
    else:
        for j in range(m.nArt):
            if m.s32(T[43], j) < 30:
                continue
            cc, cov = connectivity(m, j)
            if cc >= 3:
                ub0 = m.s32(T[35], j)
                ops = [round(m.f32(T[68], ub0+k), 2) for k in range(m.s32(T[36], j))]
                cand.append((cc, j, ids[j], m.s32(T[41], j), m.s32(T[43], j), m.s32(T[46], j)//3, cov, ops))
        cand.sort(reverse=True)
        for cc, j, nm, tex, nv, nt, cov, ops in cand[:20]:
            print("  块=%3d  #%3d %-12s tex=%d vtx=%4d tris=%4d 覆盖=%.2f 透明度=%s" % (cc, j, nm, tex, nv, nt, cov, ops))
        if not cand:
            print("  （无）")

    print("\n== 建议 ==")
    print("  · 有 B 命中 → 该部件下的网格就是水印，直接整组删")
    print("  · 有 C 命中 → 孤儿网格按 D 的连通块数排序，最大的那组通常是水印文字")
    print("  · 都没有 → 水印可能画在贴图里，改用 scripts/scan_texture.py 扫贴图")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
