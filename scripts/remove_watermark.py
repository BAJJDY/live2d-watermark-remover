import sys, os, struct, shutil, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moc3 import Moc3

"""
remove_watermark.py —— 把水印网格的「几何数据」删掉（不是隐藏）。

做法（对每个要删的网格）：
  1. indexCount = 0            —— 没有任何三角形可画
  2. 索引数据全写 0
  3. 顶点坐标（每个关键帧）全写 0
  4. UV 全写 0
不动 isVisible / 不透明度 / 参数范围，所以不是"隐藏"，是数据没了。

用法:
    python3 remove_watermark.py <输入moc3> <输出moc3> <网格索引,逗号分隔> [--erase-tex 贴图:t_x0,y0,x1,y1 ...]

注意：不要改原始文件，始终输出到副本。
"""

def main(src, dst, idx_list, erase=()):
    m = Moc3(src); T = m.T
    b = bytearray(m.b); N = len(b)
    VC, UB, UV, IDXB, IDXC, PI = T[43], T[44], T[78], T[45], T[46], T[79]
    KFB, KFC, APB, KP = T[35], T[36], T[70], T[71]
    ids = m.ids(m.artIds, m.nArt)

    def zero(off, ln, label):
        assert 0 <= off and off + ln <= N, "%s 越界: off=%d len=%d" % (label, off, ln)
        b[off:off+ln] = b'\x00' * ln

    for i in idx_list:
        n = m.s32(VC, i); ic = m.s32(IDXC, i); ib = m.s32(IDXB, i); ub = m.s32(UB, i)
        begin = m.s32(KFB, i); cnt = m.s32(KFC, i)
        struct.pack_into('<I', b, IDXC + 4*i, 0)
        zero(PI + ib*2, ic*2, 'idx')
        zero(UV + 4*ub, 2*n*4, 'uv')
        for k in range(cnt):
            zero(KP + 4*m.s32(APB, begin+k), 2*n*4, 'pos%d' % k)
        print("#%-4d %-12s indexCount %5d -> 0 | 顶点 %4d × %d 关键帧 / UV / 索引 清零" % (i, ids[i], ic, n, cnt))

    if erase:
        from PIL import Image
        import numpy as np
        by_tex = {}
        for spec in erase:
            tex, box = spec.split(':')
            x0, y0, x1, y1 = [int(v) for v in box.split(',')]
            by_tex.setdefault(int(tex), []).append((x0, y0, x1, y1))
        modeldir = os.path.dirname(os.path.abspath(dst))
        for tex, boxes in by_tex.items():
            # 贴图目录名形如 xxx.2048 / xxx.8192，在模型目录里递归找
            cand = None
            for dp, dns, fns in os.walk(modeldir):
                if ('texture_%02d.png' % tex) in fns:
                    cand = os.path.join(dp, 'texture_%02d.png' % tex); break
            assert cand, "找不到 texture_%02d.png（--erase-tex 需要在解好的模型目录里跑）" % tex
            im = Image.open(cand).convert('RGBA'); a = np.array(im)
            for x0, y0, x1, y1 in boxes:
                a[y0:y1, x0:x1, 3] = 0
            Image.fromarray(a).save(cand)
            print("贴图 texture_%02d.png 擦除 %s" % (tex, boxes))

    o = bytes(m.b)          # 原始字节（在写入之前就取好，src==dst 也不会算错）
    new = bytes(b)
    open(dst, 'wb').write(new)
    diff = sum(1 for x, y in zip(o, new) if x != y)
    print("\n输出 %s" % dst)
    print("  体积 %d -> %d (%s)" % (len(o), len(new), "相同" if len(o) == len(new) else "变了！"))
    print("  不同字节 %d" % diff)
    print("  sha256 原 %s" % hashlib.sha256(o).hexdigest()[:16])
    print("  sha256 新 %s" % hashlib.sha256(new).hexdigest()[:16])
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    idx = [int(x) for x in sys.argv[3].split(',') if x.strip()]
    erase = []
    if '--erase-tex' in sys.argv:
        k = sys.argv.index('--erase-tex')
        erase = sys.argv[k+1:]
    sys.exit(main(sys.argv[1], sys.argv[2], idx, erase))
