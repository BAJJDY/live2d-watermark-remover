import json, os, sys, glob, argparse, re

"""
strip_meta.py —— 几何删完之后，把"水印"这层元数据也清掉。

清什么：
  · *.cdi3.json 里 Parameters / Parts 中名字带 水印/声明/作者/禁止/转载/署名 的条目
    （参数分组、组合参数里的引用一并过滤，避免悬空 id）
  · 文件名带这些词的 *.exp3.json：把 Parameters 清空 → 变成空操作
  · *.vtube.json 里引用上述表情的热键

用法：
    python3 strip_meta.py <模型目录或单文件> [--dry-run]
"""

WM = re.compile(r'(水印|声明|作者|禁止|转载|署名)', re.I)


def clean_cdi(path, dry=False):
    d = json.load(open(path, encoding='utf-8'))
    removed = []
    for key in ('Parameters', 'Parts'):
        arr = d.get(key)
        if not isinstance(arr, list):
            continue
        keep = []
        for it in arr:
            if WM.search((it.get('Id') or '') + (it.get('Name') or '')):
                removed.append('%s:%s/%s' % (key, it.get('Id'), it.get('Name')))
            else:
                keep.append(it)
        d[key] = keep
    alive = {it.get('Id') for k in ('Parameters', 'Parts') for it in (d.get(k) or [])}
    for g in d.get('ParameterGroups') or []:
        if 'Ids' in g:
            g['Ids'] = [i for i in g['Ids'] if i in alive]
    for cp in d.get('CombinedParameters') or []:
        if 'Ids' in cp:
            cp['Ids'] = [i for i in cp['Ids'] if i in alive]
    if not dry:
        open(path, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=4))
    return removed


def neutralise_exp(path, dry=False):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception:
        d = {'Type': 'Live2D Expression', 'Parameters': []}
    d['Parameters'] = []
    if not dry:
        open(path, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=4))
    return os.path.basename(path)


def clean_vtube(path, dry=False):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception:
        return []
    removed = []
    keep = []
    for h in d.get('Hotkeys') or []:
        if WM.search((h.get('File') or '') + (h.get('Name') or '')):
            removed.append(h.get('File') or h.get('Name'))
        else:
            keep.append(h)
    d['Hotkeys'] = keep
    if not dry:
        open(path, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2))
    return removed


def run(root, dry=False):
    print('目录:', root, '（dry-run）' if dry else '')
    n = 0
    for cdi in glob.glob(os.path.join(root, '**', '*.cdi3.json'), recursive=True):
        r = clean_cdi(cdi, dry)
        if r:
            n += len(r)
            print('  cdi3 去掉条目:', r)
    for exp in glob.glob(os.path.join(root, '**', '*.exp3.json'), recursive=True):
        if WM.search(os.path.basename(exp)):
            n += 1
            print('  清空表情:', neutralise_exp(exp, dry))
    for vt in glob.glob(os.path.join(root, '**', '*.vtube.json'), recursive=True):
        r = clean_vtube(vt, dry)
        if r:
            n += len(r)
            print('  vtube 去掉热键:', r)
    print('  合计处理 %d 处' % n)
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    sys.exit(run(a.path, a.dry_run))
