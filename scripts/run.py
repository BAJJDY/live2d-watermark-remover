import sys, os, json, shutil, zipfile, argparse, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from moc3 import Moc3

"""
run.py —— 「去水印」统一入口。任何 AI / 任何机器都能用，不依赖特定平台。

四个子命令:
  analyze   找出水印入口（参数名 / 部件名 / 孤儿网格 / 文字几何）
  apply     在【副本】上删掉水印几何，可选擦贴图，可选直接打包
  verify    结构自检（纯 Python）；有 node 时再跑官方 Cubism Core 校验
  pack      把目录打成 zip，顶层目录名可指定

例子:
  python3 run.py analyze ./model
  python3 run.py apply  ./model --out ./out/model --meshes 522,523,524,525,526,527 --pack ./out/model_去水印.zip
  python3 run.py verify ./out/model

依赖:
  必需  python3
  推荐  pillow numpy        （apply 擦贴图 / analyze 判文字几何时用）
  可选  scipy               （analyze 的连通块统计；没有就退化成只看透明度曲线）
  可选  node                （verify 用官方 Cubism Core 做权威判定）
"""

def find_moc3(root):
    """兼容单文件 / 单模型 / 整包（可能含多个 moc3，例如多套衣服）"""
    if os.path.isfile(root) and root.lower().endswith('.moc3'):
        return root
    for dp, dns, fns in os.walk(root):
        for f in fns:
            if f.lower().endswith('.moc3'):
                return os.path.join(dp, f)
    return None


def all_moc3(root):
    if os.path.isfile(root) and root.lower().endswith('.moc3'):
        return [root]
    out = []
    for dp, dns, fns in os.walk(root):
        for f in sorted(fns):
            if f.lower().endswith('.moc3'):
                out.append(os.path.join(dp, f))
    return out


def cmd_analyze(a):
    import find_watermark, plan as planmod
    mocs = [a.model] if a.model else all_moc3(a.path)
    if not mocs:
        print('找不到 .moc3'); return 1
    print('包内 moc3 共 %d 个：%s\n' % (len(mocs), [os.path.basename(x) for x in mocs]))
    for moc in mocs:
        cdi = a.cdi3 or (os.path.splitext(moc)[0] + '.cdi3.json')
        find_watermark.main(moc, cdi if os.path.exists(cdi) else None)
        print('\n---- 自动方案 ----')
        planmod.main(moc)
        print()
    return 0


def cmd_apply(a):
    import remove_watermark, plan as planmod
    from moc3 import Moc3
    src_root = a.path
    moc = a.model if a.model else find_moc3(src_root)
    if not moc:
        print('找不到 .moc3'); return 1
    if os.path.abspath(a.out).rstrip('/') == os.path.abspath(src_root).rstrip('/'):
        print('--out 不能等于输入目录（原包必须只读）'); return 1
    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    # 保持相对结构：把输入目录整体复制成输出目录
    if os.path.isdir(src_root):
        shutil.copytree(src_root, a.out)
        rel = os.path.relpath(moc, src_root)
        dst_moc = os.path.join(a.out, rel)
    else:
        os.makedirs(a.out, exist_ok=True)
        dst_moc = os.path.join(a.out, os.path.basename(moc))
        shutil.copy2(moc, dst_moc)
        for side in ('.model3.json', '.cdi3.json', '.physics3.json'):
            p = os.path.splitext(moc)[0] + side
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(a.out, os.path.basename(p)))
        d = os.path.splitext(os.path.basename(moc))[0] + '.2048'
        if os.path.isdir(os.path.join(os.path.dirname(moc), d)):
            shutil.copytree(os.path.join(os.path.dirname(moc), d), os.path.join(a.out, d))
    # 目标集合：--auto 自动判定 / --ids 按网格名 / --meshes 按索引
    targets = {}
    if a.auto:
        for src_moc in all_moc3(src_root):
            p = planmod.build_plan(src_moc)
            rel = os.path.relpath(src_moc, src_root) if os.path.isdir(src_root) else os.path.basename(src_moc)
            targets[rel] = p['meshes']
            print('自动方案 %s -> %s  理由: %s' % (rel, p['meshes'], '；'.join(p['why'])))
    elif a.ids:
        names = [x.strip() for x in a.ids.split(',') if x.strip()]
        for src_moc in all_moc3(src_root):
            m = Moc3(src_moc)
            rel = os.path.relpath(src_moc, src_root) if os.path.isdir(src_root) else os.path.basename(src_moc)
            targets[rel] = m.resolve(names)
            print('按名字解析 %s -> %s' % (rel, targets[rel]))
    else:
        idx = [int(x) for x in (a.meshes or '').split(',') if x.strip()]
        rel = os.path.relpath(moc, src_root) if os.path.isdir(src_root) else os.path.basename(moc)
        targets[rel] = idx

    erase = a.erase_tex or []
    rc = 0
    done = 0
    for dp, dns, fns in os.walk(a.out):
        for f in sorted(fns):
            if not f.endswith('.moc3'):
                continue
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, a.out)
            idx = targets.get(rel)
            if idx is None:
                print('（跳过 %s：没有给它指定目标）' % rel); continue
            print('\n== %s ==' % rel)
            rc |= remove_watermark.main(full, full, idx, erase)
            done += 1
    if not done:
        print('没有处理任何 moc3，请检查 --meshes/--ids/--auto')
    if a.pack:
        pack(a.out, a.pack, a.top)
        cmd_verify_silent(a.out)
    return rc


def pack(src_dir, out_zip, top=None):
    if os.path.exists(out_zip):
        os.remove(out_zip)
    top = top or os.path.basename(src_dir.rstrip('/'))
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(src_dir):
            for f in fns:
                full = os.path.join(dp, f)
                z.write(full, os.path.join(top, os.path.relpath(full, src_dir)))
    print('打包 %s  %.1f MB' % (out_zip, os.path.getsize(out_zip)/1048576))


def cmd_verify_silent(path):
    moc = find_moc3(path)
    print('\n== 结构自检 ==')
    subprocess.run([sys.executable, os.path.join(HERE, 'verify_py.py'), moc])
    cjs = os.path.join(HERE, 'verify.cjs')
    if shutil.which('node') and os.path.exists(cjs) and os.path.exists(os.path.join(HERE, 'cubismcore.min.js')):
        print('\n== Cubism Core 校验 ==')
        subprocess.run(['node', cjs, moc])
    else:
        print('\n（没装 node 或缺少 cubismcore.min.js，跳过官方 Core 校验）')


def cmd_verify(a):
    cmd_verify_silent(a.path)
    return 0


def cmd_pack(a):
    pack(a.path, a.out, a.top)
    return 0


def main():
    ap = argparse.ArgumentParser(description='Live2D 去水印（通用命令行）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('analyze', help='定位水印入口')
    p.add_argument('path'); p.add_argument('--model', default=None); p.add_argument('--cdi3', default=None)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser('apply', help='在副本上删除水印几何')
    p.add_argument('path'); p.add_argument('--out', required=True)
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument('--meshes', help='网格索引,逗号分隔（同一模型内）')
    g.add_argument('--ids', help='网格名字,逗号分隔（如 ArtMesh330,t5；索引会变，名字更稳）')
    g.add_argument('--auto', action='store_true', help='自动判定水印（推荐）')
    p.add_argument('--model', default=None)
    p.add_argument('--erase-tex', action='append', default=[],
                   help='贴图:起点x,起点y,终点x,终点y（可多次，区域必须独占）')
    p.add_argument('--pack', default=None, help='顺手打包到这个 zip')
    p.add_argument('--top', default=None, help='zip 里的顶层目录名')
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser('plan', help='只输出自动判定方案（JSON）')
    p.add_argument('path'); p.add_argument('--json', default=None)
    p.set_defaults(func=lambda a: (__import__('plan').main(a.path, a.json), 0)[1])

    p = sub.add_parser('verify', help='结构自检 + 可选官方 Core 校验')
    p.add_argument('path'); p.set_defaults(func=cmd_verify)

    p = sub.add_parser('pack', help='打包目录')
    p.add_argument('path'); p.add_argument('--out', required=True); p.add_argument('--top', default=None)
    p.set_defaults(func=cmd_pack)

    a = ap.parse_args()
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
