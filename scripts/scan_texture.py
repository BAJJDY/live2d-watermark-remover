import sys, os, glob
import numpy as np
from PIL import Image

"""
scan_texture.py —— 当几何里找不到文字水印时，扫贴图找"印章式水印"。

两种典型特征：
  1. 大块半透明且 alpha 几乎恒定（水印图章常见 alpha≈0.5 的一整块）
  2. 细笔画密度高（字形笔画来回穿越 alpha 阈值）

用法:
    python3 scan_texture.py <贴图目录> [--alpha] [--edge]
"""

def alpha_uniform(path, block=256, ratio=0.85):
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    sc = min(1.0, 2024/w)
    im = im.resize((int(w*sc), int(h*sc)), Image.BOX)
    a = np.asarray(im)[..., 3]
    H, W = a.shape
    out = []
    for y in range(0, H-block, block):
        for x in range(0, W-block, block):
            blk = a[y:y+block, x:x+block].ravel()
            nz = blk[blk > 8]
            if nz.size < 3000:
                continue
            v, cnt = np.unique(nz, return_counts=True)
            top = cnt.max()/nz.size
            if top > ratio and v[cnt.argmax()] < 245:
                out.append((int(x/sc), int(y/sc), int(v[cnt.argmax()]), round(float(top), 2)))
    return out


def edge_density(path, block=64):
    im = Image.open(path).convert('RGBA')
    w, h = im.size
    sc = min(1.0, 2024/w)
    im = im.resize((int(w*sc), int(h*sc)), Image.BOX)
    a = np.asarray(im)[..., 3]
    b = (a > 0.5).astype(np.uint8)
    dx = np.abs(np.diff(b, axis=1)).sum(axis=1)
    H = len(dx)
    rows = []
    for y in range(0, H-block, block):
        rows.append((int(dx[y:y+block].sum()), int(y/sc)))
    rows.sort(reverse=True)
    return rows[:5]


def main(texdir, modes):
    files = sorted(glob.glob(os.path.join(texdir, 'texture_*.png')))
    if not files:
        print("没找到 texture_*.png：%s" % texdir); return 1
    for f in files:
        print("==", os.path.basename(f), Image.open(f).size)
        if 'alpha' in modes or not modes:
            hits = alpha_uniform(f)
            print("  恒定 alpha 块:", len(hits), hits[:5])
        if 'edge' in modes or not modes:
            print("  细笔画最密的行块:", edge_density(f))
    print("\n命中区域请按 4x 放大裁出来人眼看；确认是水印后再决定擦除。")
    print("注意：只有该 UV 区域【独占】于水印网格时才能擦贴图，否则会连带毁掉别的部件。")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    sys.exit(main(sys.argv[1], set(sys.argv[2:])))
