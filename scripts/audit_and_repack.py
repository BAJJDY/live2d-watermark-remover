import sys, os, json, hashlib, zipfile, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moc3 import Moc3

"""
audit_and_repack.py —— 出包前的核对 + 打包。原包只读，只动副本。

核对内容:
  1. moc3 体积 / 结构（网格数、参数数、部件数、变形器数）
  2. 除目标网格外，其它网格的 10 个关键字段是否完全一致
  3. 参数的 min/max/default 是否有变化
  4. 目录内所有文件 sha256 比对（应当只有 moc3 变）
  5. 调 Cubism Core 加载 + csmHasMocConsistency + 索引/遮罩越界检查

用法:
    python3 audit_and_repack.py <原始模型目录> <改后模型目录> <输出zip> <目标网格索引,逗号分隔> [压缩后的顶层目录名]
"""

FIELDS = [(43, 'vertexCounts'), (46, 'indexCounts'), (41, 'textureNo'), (44, 'uvBegin'), (45, 'idxBegin'),
          (39, 'parentPart'), (40, 'parentDeformer'), (37, 'isVisible'), (38, 'isEnabled'), (48, 'maskCounts')]


def find_moc3(root):
    for dp, dns, fns in os.walk(root):
        for f in fns:
            if f.lower().endswith('.moc3'):
                return os.path.join(dp, f)
    return None


def main(src_root, dst_root, out_zip, targets, top_name=None):
    a = Moc3(find_moc3(src_root)); c = Moc3(find_moc3(dst_root))
    print("== 结构 ==")
    print("  counts 一致: %s | 网格 %d 参数 %d 部件 %d 变形器 %d" % (a.counts == c.counts, c.nArt, c.nParam, c.nParts, c.nDef))
    print("  体积 %d -> %d" % (len(a.b), len(c.b)))

    print("== 网格字段 ==")
    bad = 0
    for ptr, name in FIELDS:
        d = [i for i in range(c.nArt) if a.s32(a.T[ptr], i) != c.s32(c.T[ptr], i)]
        if d:
            print("  %s 变化: %s" % (name, d))
            if set(d) - set(targets):
                bad += 1
                print("    ⚠ 目标之外的网格被改了")
    keep_ok = all(a.s32(a.T[p], i) == c.s32(c.T[p], i) for p, _ in FIELDS
                  for i in range(c.nArt) if i not in targets)
    print("  其余网格字段完全一致:", keep_ok)

    print("== 参数 ==")
    ch = [i for i in range(c.nParam)
          if (a.f32(a.T[51], i), a.f32(a.T[52], i), a.f32(a.T[53], i)) !=
             (c.f32(c.T[51], i), c.f32(c.T[52], i), c.f32(c.T[53], i))]
    print("  min/max/default 变化数:", len(ch))

    print("== 文件 sha256 ==")
    diffs, total = [], 0
    for dp, dns, fns in os.walk(src_root):
        for f in fns:
            src = os.path.join(dp, f)
            rel = os.path.relpath(src, src_root)
            dst = os.path.join(dst_root, rel)
            total += 1
            if not os.path.exists(dst):
                diffs.append(rel + "（缺失）"); continue
            h1 = hashlib.sha256(open(src, 'rb').read()).hexdigest()
            h2 = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
            if h1 != h2:
                diffs.append(rel)
    print("  文件数 %d，改动: %s" % (total, diffs))

    # Core 校验（可选：需要 node + scripts/cubismcore.min.js + verify.cjs）
    here = os.path.dirname(os.path.abspath(__file__))
    verify = os.path.join(here, 'verify.cjs')
    if shutil.which('node') and os.path.exists(verify):
        print("== Cubism Core 校验 ==")
        try:
            r = subprocess.run(['node', verify, find_moc3(dst_root)], capture_output=True, text=True, timeout=300)
            print(r.stdout.strip()[-800:])
        except Exception as e:
            print("  校验脚本失败:", e)
    else:
        print("== 跳过 Core 校验（没装 node 或缺少 verify.cjs）==")

    print("== 打包 ==")
    if os.path.exists(out_zip):
        os.remove(out_zip)
    top = top_name or os.path.basename(dst_root.rstrip('/'))
    parent = os.path.dirname(dst_root.rstrip('/'))
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(dst_root):
            for f in fns:
                full = os.path.join(dp, f)
                z.write(full, os.path.join(top, os.path.relpath(full, dst_root)))
    print("  %s  %.1f MB" % (out_zip, os.path.getsize(out_zip)/1048576))
    return 0 if (bad == 0 and keep_ok) else 1


if __name__ == '__main__':
    if len(sys.argv) < 5:
        print(__doc__); sys.exit(1)
    t = [int(x) for x in sys.argv[4].split(',') if x.strip()]
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], t, sys.argv[5] if len(sys.argv) > 5 else None))
