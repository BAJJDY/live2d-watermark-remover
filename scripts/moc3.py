import struct

"""
moc3.py —— 极简 moc3（Live2D Cubism 3 / 4 / 4.2 / 5）解析器。

只做"够用"的事：
  · 段指针表（0x40 起，前 152 个是真指针）
  · counts 表（位置随版本不同，用部件/网格 id 数量自适应判断）
  · 参数 / 网格 / 部件 / 变形器的 id 与关键字段
  · UV / 位置 / 索引 / 遮罩 / 绘制组 / 透明度关键帧

用法：
    m = Moc3('model.moc3')
    m.nArt, m.nParam, m.nParts, m.nDef
    m.ids(m.artIds, m.nArt)
    m.u32(m.T[43], 0)          # 网格 0 的顶点数
"""


class Moc3:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.b = f.read()
        assert self.b[:4] == b'MOC3', '不是 moc3 文件'
        self.T = [struct.unpack_from('<I', self.b, 0x40 + 4*i)[0] for i in range(0x260)]
        self.ver = self.b[4] if len(self.b) > 4 else 0
        self.counts_off = self._detect_counts_off()
        base = self.T[0] + self.counts_off
        self.counts = [struct.unpack_from('<I', self.b, base + 4*i)[0] for i in range(40)]
        c = self.counts
        (self.nParts, self.nDef, self.nWarp, self.nRot, self.nArt, self.nParam,
         self.nPartKf, self.nWarpKf, self.nRotKf, self.nArtKf, self.nKfPos,
         self.nPbi, self.nKfBind, self.nParamBind, self.nKeys) = c[:15]

    # ---------- 版本自适配 ----------
    def _detect_counts_off(self):
        """counts 表在 countInfo 段内的偏移随 moc3 版本不同（v5 的头部 padding 与 v3/v4 不一样）。
        用「部件 id 数 / 网格 id 数」反推，选能同时对上的偏移。"""
        try:
            nparts = self._count_ids(self.T[3])
            narts = self._count_ids(self.T[33])
        except Exception:
            return 0
        for off in (0, 0x100, 0x80):
            try:
                parts = struct.unpack_from('<I', self.b, self.T[0] + off)[0]
                arts = struct.unpack_from('<I', self.b, self.T[0] + off + 16)[0]
            except Exception:
                continue
            if parts == nparts and arts == narts:
                return off
        return 0

    def _count_ids(self, p, maxn=8192):
        """数 64 字节 id 记录，遇到全 0 或非可打印内容就停"""
        n = 0
        while n < maxn:
            seg = self.b[p + 64*n: p + 64*n + 64]
            if len(seg) < 64 or seg[0] == 0:
                break
            s = seg.split(b'\0')[0]
            if not s or not all(32 <= ch <= 126 or ch >= 0x80 for ch in s):
                break
            n += 1
        return n

    # ---------- 基础访问 ----------
    def u32(self, p, i): return struct.unpack_from('<I', self.b, p + 4*i)[0]
    def s32(self, p, i): return struct.unpack_from('<i', self.b, p + 4*i)[0]
    def f32(self, p, i): return struct.unpack_from('<f', self.b, p + 4*i)[0]

    def ids(self, p, n):
        out = []
        for i in range(n):
            s = self.b[p + 64*i: p + 64*i + 64].split(b'\0')[0]
            out.append(s.decode('utf-8', 'replace'))
        return out

    # ---------- 段指针（各版本前部顺序一致，V4.2/V5 段一律追加在后） ----------
    @property
    def partIds(self): return self.T[3]
    @property
    def artIds(self): return self.T[33]
    @property
    def paramIds(self): return self.T[50]

    # ---------- 常用查询 ----------
    def param_index(self, pid):
        return self.ids(self.paramIds, self.nParam).index(pid)

    def drawable_index(self, name):
        return self.ids(self.artIds, self.nArt).index(name)

    def resolve(self, names):
        """把名字列表解析成索引列表（名字不存在会抛出可读错误）"""
        allids = self.ids(self.artIds, self.nArt)
        out = []
        for nm in names:
            if nm not in allids:
                raise KeyError('模型里没有名为 %r 的网格' % nm)
            out.append(allids.index(nm))
        return out

    def keyform_bindings(self, kf):
        b0 = self.s32(self.T[73], kf)
        cnt = self.s32(self.T[74], kf)
        return [self.s32(self.T[72], b0 + k) for k in range(cnt)]

    def binding_keys(self, binding):
        s = self.s32(self.T[75], binding)
        n = self.s32(self.T[76], binding)
        return [self.f32(self.T[77], s + k) for k in range(n)]
