# 去水印（Live2D .moc3）

跨平台、纯命令行的 Live2D 去水印工具包 + 一份给 AI 用的作业说明书。

- 说明书（AI 先读这个）：[`SKILL.md`](SKILL.md)
- 统一入口：`python3 scripts/run.py {analyze|apply|verify|pack} ...`

```bash
git clone https://github.com/BAJJDY/live2d-watermark-remover.git
cd live2d-watermark-remover
pip install -r requirements.txt      # 全部可选，只装 python3 也能跑
```

> **关于 `scripts/cubismcore.min.js`**
> 官方 Cubism Core 由 Live2D 分发，本仓库不再二次分发（已在 `.gitignore` 排除）。
> 想用「官方 Core 权威校验」时，自己从 [Live2D 官网](https://www.live2d.com/download/cubism-sdk/) 取
> `live2dcubismcore.min.js`，改名为 `cubismcore.min.js` 放进 `scripts/` 即可；
> 不放也能跑 —— `verify_py.py` 会做纯 Python 结构自检。

## 30 秒上手

```bash
python3 scripts/run.py analyze ./model                       # 看它挂在哪、理由是什么
python3 scripts/run.py apply ./model --out ./out/model --auto --pack ./out/model_去水印.zip
python3 scripts/run.py verify ./out/model
```

`./model` 可以是模型目录、单个 `.moc3`，或整包（多个 moc3 会逐个处理）。
目标也能按名字指定：`--ids ArtMesh330,ArtMesh336,t5`（跨版本不错位）。

## 适用面

- moc3 **3.0 / 3.3 / 4.0 / 4.2 / 5**：段指针布局一致，`counts` 偏移用部件/网格 id 数自适应探测；
- 水印五种形态：参数驱动、部件驱动、孤儿全屏层、文字几何、贴图印章；
- 几百~上千网格、8192 贴图都能跑；
- 纯 `python3` + 相对路径，Linux / macOS / Windows 通用；Pillow / numpy / scipy / node 全部可选。

## 更新记录

- **判定加门槛**：`has_geom()`（空网格不参与）+ 可信度门槛（种子连通块 ≥3 且家族含孤儿，或整组孤儿）
  + 规则 3 门槛提到 ≥6 块 + 孤儿跨度规则要求 `parentDef=-1`。
  这几条是为了修一个真实误判：拿处理过的成品再丢进来，会把 `ArtMesh21/ArtMesh35` 当成水印。
- **新增 `strip_meta.py`**：几何删完之后，把 cdi3 里的"水印"参数/部件名、失效表情、相关热键一起清掉。
- **表情同步**：参数清空的表情不再显示。

## 它到底做了什么

1. 定位：从「参数名 / 部件名 / 孤儿网格 / 文字几何 / 贴图印章」五条路找出水印挂在哪；
2. 取证：把水印网格的 UV 轮廓重绘成图，能直接读出「禁止二传 / 仅售于B站工坊与BOOTH」这类原文；
3. 移除：`indexCount=0` + 索引 / 顶点（每帧）/ UV 全清零 —— 删数据，不改透明度、不改可见性；
4. 验证：纯 Python 结构自检；有 node 时再跑官方 Cubism Core（`ver=5`、`consistency=1`）；
5. 清元数据：`strip_meta.py` 去掉 cdi3 名字 / 失效表情 / 热键；
6. 打包：原包只读，产物只含副本。

## 不装依赖也能用

只装 python3 就能跑 `analyze`（A/B/C 段）、`apply`、`verify`、`pack`。
`pillow`/`numpy` 用于擦贴图和 D 段连通块统计，`node` 用于官方 Core 校验——缺了就自动跳过并提示。
