import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moc3 import Moc3

"""
verify_py.py —— 纯 Python 的 moc3 自检（不需要 node / Cubism Core）。

检查项:
  1. 文件头 MOC3、moc3 版本字节
  2. counts 表与各段指针是否落在文件内
  3. 逐网格：UV / 索引 / 关键帧 / 遮罩 / 父部件 / 父变形器 的边界
  4. 参数：pbi 区间、keyform 绑定区间
  5. 绘制组：begin/count 与对象索引越界
  6. 遮罩里引用的网格索引越界

用法:
    python3 verify_py.py <moc3> [更多moc3...]

返回码 0 = 全部通过。
说明：这是"结构自检"，比 Cubism Core 的 csmHasMocConsistency 宽松；
      手边有 node 时优先用 verify.cjs（那是官方 Core 的判定）。
"""

def check(path):
    problems = []
    info = {}
    m = Moc3(path); T = m.T
    b = m.b; N = len(b)
    info['file'] = os.path.basename(path)
    info['size'] = N
    if b[:4] != b'MOC3':
        problems.append('文件头不是 MOC3')
    info['moc_version'] = b[4] if len(b) > 4 else -1

    # 段指针
    for i, p in list(enumerate(T))[:152]:   # 只有前 152 个是真段指针
        if p == 0:
            continue
        if p > N:
            problems.append('段指针[%d]=0x%x 超出文件' % (i, p))

    VC, UB, UV, IDXB, IDXC, PI = T[43], T[44], T[78], T[45], T[46], T[79]
    KFB, KFC = T[35], T[36]
    uv_total = m.counts[15]; idx_total = m.counts[16]; kf_total = m.counts[9]
    mask_total = m.counts[17]

    bad = 0
    for i in range(m.nArt):
        n = m.s32(VC, i); ic = m.s32(IDXC, i)
        if n < 0 or ic < 0:
            problems.append('网格 %d 顶点/索引数为负' % i); bad += 1; continue
        ub = m.s32(UB, i); ib = m.s32(IDXB, i)
        if n and (ub + 2*n > uv_total):
            problems.append('网格 %d UV 越界' % i); bad += 1
        if ic and (ib + ic > idx_total):
            problems.append('网格 %d 索引越界' % i); bad += 1
        if m.s32(KFB, i) + m.s32(KFC, i) > kf_total:
            problems.append('网格 %d 关键帧越界' % i); bad += 1
        pp = m.s32(T[39], i); pd = m.s32(T[40], i)
        if pp >= m.nParts or pd >= m.nDef:
            problems.append('网格 %d 父部件/父变形器越界' % i); bad += 1
        mb = m.s32(T[47], i); mc = m.s32(T[48], i)
        if mc and mb + mc > mask_total:
            problems.append('网格 %d 遮罩区间越界' % i); bad += 1
        for k in range(mc):
            v = m.s32(T[80], mb + k)
            if v == -1:
                continue
            if v < 0 or v >= m.nArt:
                problems.append('网格 %d 遮罩引用越界 %d' % (i, v)); bad += 1; break
    info['bad_drawables'] = bad

    # 参数
    pbi_total = m.counts[11]
    badp = 0
    for i in range(m.nParam):
        s = m.s32(T[56], i); c = m.s32(T[57], i)
        if c and s + c > pbi_total:
            problems.append('参数 %d 绑定区间越界' % i); badp += 1
    info['bad_params'] = badp

    # 绘制组
    nobj = m.counts[19]
    for g in range(m.counts[18]):
        s = m.s32(T[81], g); c = m.s32(T[82], g)
        if c and s + c > nobj:
            problems.append('绘制组 %d 对象区间越界' % g)
    for k in range(nobj):
        t = m.u32(T[86], k); v = m.s32(T[87], k)
        if t == 0 and (v < 0 or v >= m.nArt):
            problems.append('绘制组对象 %d 引用网格越界' % k); break
        if t == 1 and (v < 0 or v >= m.nParts):
            problems.append('绘制组对象 %d 引用部件越界' % k); break

    info['drawables'] = m.nArt
    info['params'] = m.nParam
    info['parts'] = m.nParts
    info['deformers'] = m.nDef
    info['problems'] = problems[:20]
    info['pass'] = not problems
    return info


def main(paths):
    ok = True
    for p in paths:
        try:
            r = check(p)
        except Exception as e:
            r = {'file': p, 'pass': False, 'problems': ['解析失败: %s' % e]}
        print(json.dumps(r, ensure_ascii=False, indent=1))
        ok = ok and r.get('pass')
    print('\n结果:', '全部通过' if ok else '有问题')
    return 0 if ok else 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    sys.exit(main(sys.argv[1:]))
