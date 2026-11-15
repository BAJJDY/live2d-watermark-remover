# 两个真实模型的完整命令记录

## 例 1：几何水印挂在「参数」上（模型 322 网格）

```bash
python3 scripts/run.py analyze ./妹妹
#  → A 段命中 param #0 Param127 / 水印 (min/max/default = 0/10/0)
#  → C 段列出 17 个孤儿网格，其中 #310/#319/#320/#321 是 parentDef=-1 的全屏网格
#  → D 段：#320/#321 连通块 7/5 块，明显是文字

python3 scripts/run.py apply ./妹妹 --out ./out/妹妹 \
    --meshes 300,301,310,319,320,321 \
    --erase-tex 0:543,12,1341,835 \
    --pack ./out/妹妹_去水印.zip

python3 scripts/run.py verify ./out/妹妹
#  → verify_py: pass=true
#  → Core: ver=5 consistency=1 drawables=322 params=173 parts=54
#  → 体积 16495744 不变，改动 107232 字节
```

## 例 2：几何水印挂在「部件」上（模型 556 网格）

```bash
python3 scripts/run.py analyze ./单独模型+UI
#  → B 段命中 部件 #1 「Part37 / 水印」，下挂网格 [522,523,524,525,526,527]
#  → A 段同时命中 param #0 fase65 / 水印（配套 去水印.exp3.json 对它 Add 1.0）

python3 scripts/run.py apply ./单独模型+UI --out ./out/单独模型+UI \
    --meshes 522,523,524,525,526,527 \
    --pack ./out/千金芭蕾_去水印.zip

python3 scripts/run.py verify ./out/单独模型+UI
#  → Core: ver=5 consistency=1 drawables=556 params=254 parts=87
#  → 体积 8550336 不变，改动 84035 字节
```

## 判读要点

- `analyze` 的 D 段里，**连通块数明显高于其它网格的那几个**就是文字水印，其余（1~3 块）是正常美术。
- 若水印由参数控制，`去水印.exp3.json` 里 `Add` 的极性就是"隐藏态"，可用来交叉验证删的是不是同一批网格。
- 删之前务必确认该网格**没有被别的网格当遮罩用**（D 段旁边会打透明度关键帧；遮罩要用 `moc3.py` 的 `T[47]/T[48]/T[80]` 查）。


## 例 3：回归——拿成品再跑一次（防误判）

```bash
python3 scripts/plan.py ./out/妹妹_去水印
# 期望：meshes 为空；理由里带「已经去过水印」或「没找到几何形态的水印」
# 若又冒出一批网格（曾出现把 ArtMesh21/ArtMesh35 当水印），说明门槛被绕过：
#   · 检查 has_geom() 是否把 indexCount=0 的网格排除了
#   · 检查可信度门槛（种子连通块 >=3 且家族含孤儿）
#   · 检查孤儿跨度规则是否要求 parentDef=-1
```

## 例 4：清元数据残留

```bash
python3 scripts/strip_meta.py ./out/妹妹_去水印 --dry-run
#  → cdi3 去掉条目: ['Parameters:Param127/水印']
#  → 清空表情: 水印消失.exp3.json
#  → vtube 去掉热键: ['水印消失.exp3.json']

python3 scripts/strip_meta.py ./out/妹妹_去水印
grep -ril 水印 ./out/妹妹_去水印      # 只应剩下你自己的说明文件
```
