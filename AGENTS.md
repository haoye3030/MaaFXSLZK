# AGENTS.md

MaaFXSLZK —— 《拂晓：胜利之刻》MaaFramework 自动化助手。pipeline 项目 + `agent/` python 扩展层（自定义识别器）。

**本文件每次会话都会被自动读取。只放"动手前必须知道"的内容；需要细节时读文末链接的深文档。**

## 一、工作目录

| 用途 | 路径 |
|---|---|
| 仓库根（**只改这里**） | `E:\DSH\MaaFX\MaaFXSLZK` |
| 运行副本（同步产物，不要手改） | `E:\DSH\MaaFX\release\win-x64` |
| pipeline | `assets/resource/pipeline/*.json`（13 个文件，**全局节点空间共用**） |
| agent 扩展 | `agent/recognizers.py`（识别器类）+ `agent/main.py`（AgentServer 入口），由 `interface.json` 的 `agent` 字段拉起 |
| agent venv | `E:\DSH\MaaFX\agent-venv`（**maafw==5.10.0 协议 7，不可升级**，仓库/release 之外） |
| 素材 | `assets/resource/image/<功能>/`，共 93 张 |
| 任务入口 | `assets/interface.json`（**JSONC，允许 `//` 注释**，标准 `json.loads` 会失败） |
| 模拟器 | MuMu，adb `C:/Program Files/Netease/MuMu/nx_main/adb.exe`，设备 `127.0.0.1:16384` |
| 失败截图 | `debug/on_error/`（`save_on_error` 自动产出，文件名 = 时间戳\_节点名） |

## 二、铁律（违反会造成静默失败或返工）

1. **分辨率单基准 1280×720。** 所有 `roi` / `target` 按此写死，不做多分辨率兼容。
2. **`next` 只在当前节点识别成功后才遍历。** 识别失败直接走 `on_error`。要分支就让当前节点 `DirectHit` 兜住，把判断下沉到 `next` 里的具体节点。
3. **`DirectHit` + 固定坐标点击永远不会失败。** 关键动作后**必须**跟一个结果校验节点（TemplateMatch 目标状态），否则失败完全静默。
4. **`inverse` 触发 `on_error` 要等自己的 `timeout` 耗尽。** 这个节点的 `timeout` 就是等待时长，别设大。
5. **`timeout` 沿链传递。** 入口节点给足预算（现有功能多为 120000~300000），上游过短会提前掐断下游的 `on_error`。
6. **改 pipeline 前先读同功能的现有写法**，命名用 `<功能><动作>` 驼峰（如 `BeachFindSlot`、`ExpRow1`）。
7. **新增功能必须过素材三项校验**：非纯色（标准差 > 15）、目标位 NCC ≥ 0.9、干扰位 NCC 明显更低。
8. **不可逆操作**（合成 / 购买 / 退役 / 建造 / 钻石刷新）必须在 `interface.json` 的 `description` 里标 ⚠️，并保留消耗前后校验。
9. **只改仓库根，不要改 `release/`。** 改完用 `sync_resource.bat` 同步。
10. **agent 扩展铁律**：Agent 协议不跨版本兼容（5.10 客户端只能连 5.10 服务端），agent-venv 锁定 maafw==5.10.0；识别器 analyze 永不抛异常（异常被 ctypes 吞掉且默认按成功处理）；predicate 类 Custom 节点给短 timeout（失败会按节点 timeout 反复重试）；改 `agent/` 或 `interface.json` 后需**重启 MFAAvalonia** 才生效。
11. **时间类逻辑走 agent 识别器**（`ExpTimeCheck`/`ExpIsNightWindow` 直接读系统时钟），不要 OCR 游戏内时钟。

## 三、常用命令

```powershell
cd E:\DSH\MaaFX\MaaFXSLZK

# 一条命令跑完全部校验（提交前必跑，等同 CI）
python tools/validate.py
python tools/validate.py --assets     # 额外跑素材检查
python tools/validate.py --fast       # 不联网时跳过 maa-tools

# 素材校验
python tools/check_assets.py            # 静态 + 读日志真实得分
python tools/check_assets.py --static    # 只做静态检查

# agent 扩展 e2e（协议 7 生产配对：5.10 客户端 + 5.10 子进程）
& "E:\DSH\MaaFX\agent-venv\Scripts\python.exe" "E:\DSH\MaaFX\tmp\agent_e2e_client.py"

# 跑任务（替代散落的一次性脚本）
python tools/run_task.py --list
python tools/run_task.py BeachStart
python tools/run_task.py --all

# 失败台账：这个功能历史上在哪些节点真的失败过
python tools/failure_ledger.py

# 同步到运行副本
..\sync_resource.bat
```

`tools/validate.py` 内含两条独立检查，**不可互相替代**：

| 检查 | 抓什么 |
|---|---|
| JSON Schema | 格式合法性：字段拼错、类型错误、用了 schema 里没有的字段 |
| maa-tools check | 语义合法性：JSON 重复键、`next` 指向不存在的节点、资源引用断裂 |

⚠️ **JSON 重复键 MAA 会报 `load_all_json failed`，但 Python 的 `json.loads` 静默通过** —— 所以 maa-tools 那步不能跳。

## 三之二、每种输入该从哪拿（血泪教训）

| 想确认的事 | 正确来源 | 别用它 |
|---|---|---|
| 模板匹配得分 | `maafw.log` 的 `TemplateMatcher::analyze` 行 | ❌ `vision/` 调试图 —— **上面画了 ROI 框和 Score 文字，标注像素污染匹配区**，自算 NCC 会得到 0.82 而 Maa 实际 1.000 |
| 原始截图 | `on_error/*.png`（干净 1280×720） | ❌ `vision/*.jpg` —— 右侧拼接了模板对照栏，宽度 1330~1488，**不是原始帧** |
| 真的失败在哪 | `on_error/` 截图文件名里的节点名 | ❌ 日志里的 `Node.Recognition.Failed` —— 那只是"这次没匹配上"，在 `next` 里逐个试探候选节点是**正常操作**，统计它会虚高十几倍 |

## 四、新功能开工流程

**不要直接写 pipeline。按顺序走：**

1. **手动跑一遍**：在模拟器里从主界面点完整流程，记下每一步的界面与按钮。摸不清入口的功能不做。
2. **列异常状态清单**：先跑 `python tools/failure_ledger.py`，看同类功能历史上栽在哪些节点。逐个回答"我这里会不会遇到"。
3. **截素材**：用 VS Code 扩展 `Maa Pipeline Support` 的截图工具（`Ctrl+Shift+P` → `Maa: 打开截图工具`），"复制"拿精确 ROI。
4. **素材校验**：`python tools/check_assets.py` 必须全绿。
5. **写 pipeline**：`Start`（设 anchor）→ `NaviTarget`（目标页直达）→ `NaviCommon`（归位）→ `[Anchor]Resume` 续跑。
6. **实机跑**：`python tools/run_task.py <EntryName>`，看 `debug/on_error/` 有没有新截图。
7. **回归**：跑相邻功能，确认没有破坏共用节点（`navi.json` 被全部功能引用）。

## 五、深文档（需要时再读，不要每次全读）

| 文档 | 什么时候读 |
|---|---|
| [素材制作规范](docs/zh_cn/develop/asset_guideline.md) | 截素材、调阈值、处理假阳性、查 pipeline 语法坑清单 |
| [待完成功能清单](docs/zh_cn/develop/todo.md) | 看还剩什么、风险分级、历史踩坑记录 |
| [日常扫荡实现规格](docs/zh_cn/develop/daily_sweep_spec.md) | 动扫荡功能前必读 |

## 六、已知易错点（历史 fix 都出在这里）

| 现象 | 原因 |
|---|---|
| 任务报 `succeeded` 但什么都没做 | 弹窗遮罩：底层界面仍可见，归位判定通过但点击被挡。归位链**最优先**要有弹窗关闭节点 |
| 模板在任意纯色处得 1.0 分 | 模板裁到了纯色区域，标准差 < 15 |
| 小图标互相误匹配 | 左侧多个深色模式图标外观相近，改用英文单词模板（区分度 56~116） |
| 点完没反应 | 点击间隔被吞。实测喂食 350ms 会丢大半，改 700ms |
| 调试图里没有 `DirectHit` 节点 | 正常，`DirectHit` 不生成调试图，查 `maafw.log` 的 `node done` |
| 关卡/列表只找到前几项 | 单屏只显示 4 个，需要横向/纵向滚动 + 重新对齐 |
| 一组候选档位空转很久（每个 ~20s） | 分支节点是 `DirectHit` 却没写 `timeout`，用默认 20000ms。失败分支必须显式给短 timeout（远征 chip 用 `timeout:2400, rate_limit:600`） |
| 以为模板误匹配 | 截图时面板/弹窗其实是开着的（探针连点后残留），面板里的同名按钮才是真命中。模板校验必须用**没有面板/弹窗**的页面；判断误报前先确认当时 UI 状态 |
| 探针脚本按 back 后全乱套 | 主界面按 `keyevent 4` 会弹「是否离开游戏」确认框（取消 601,459）。探测/导航一律用 adb 点按钮，别盲按 back |
| 同一道具的两张固定裁切互比，判成「不同道具」 | 行内小图标在图标框里的绘制位置会差几像素（数量位数、美术自带偏移），固定裁切互比只有 0.65 左右。模板校验必须用**滑动 NCC**（在行 ROI 内滑动取最高分），同一美术可达 0.94~1.000；提取/校验脚本见 `E:\DSH\MaaFX\tmp\extract_exp_tpls.py` |
| 入口任务 4 秒内硬失败（如远征点「快速领取」全灭后整任务 FAILED） | **next 列表里的候选节点自己的 `on_error` 不会执行**，候选全失败会冒泡成父节点错误。父节点必须自己写 `on_error`（`ExpOnMain` 就是漏了这个）；需要兜底的分支要塞进父节点 `next` 列表 |
| 「工作完成」快速领取抽屉盖住主界面，点不到「快速领取」 | 抽屉打开时底部导航条仍可见，`ui_main` 照样命中，视觉判定不出。共享节点 `NaviDrawerClose`（`navi.json`）用 OCR 判 `.*(炼油厂|便利店).*` ROI `[570,55,220,150]` → 点 (300,400) 关抽屉；已接入 `NaviOnMain.next` / `ExpOnMain.next` / `BeachOnMain.next` |
| 直连 OCR 只吐一条垃圾文本（整个 ROI 一个框、低分） | `JOCR(only_rec=True)` 不是「返回全部结果」，而是「跳过文字检测，把整块 ROI 当一行文本硬识别」。要正常识别多行文字必须 `only_rec=False`（默认），再用 `expected` 正则筛 |
