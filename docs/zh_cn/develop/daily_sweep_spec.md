# 自动扫荡日常关卡 —— 实现规格（交接文档）

> 本文档自包含，可直接交给其他 AI / 开发者执行，不依赖任何对话上下文。
> 标注说明：**[实测]** = 已用 ADB 截图核实；**[口述]** = 用户提供的操作描述；**[待确认]** = 尚未验证。

---

## ⚠️ 实测修正（2026-11-12，已完成实现并跑通）

本节修正下文若干**已被证伪**的记述，以下文内容与本节冲突时**以本节为准**。

| 原文记述 | 实测结论 |
|---|---|
| 点「确定」后「画面进入该关卡的**编队页**」 | ❌ 错。实际弹出**「获得奖励 REWARDS」结算层**，点「点击继续」后**直接回到日常页**，滚动位置保持。全程不经过编队页，**不需要任何返回键或归位逻辑**。 |
| 「完成（无独立结算弹窗）」 | ❌ 错。有独立结算层，必点一次「点击继续」，其 y 坐标随奖励物品数量浮动（单件 ≈580，满格 ≈548）。 |
| 卡片坐标为固定值 `[288,595]` 等 | ⚠️ 只对应**左滑过一次之后**的行位置。初始状态整行比之**右移 139px**（通商护航在 x=428 而非 288）。必须用模板匹配定位，不可写死。 |
| 第 2 次点同一张卡片「未弹窗」 | ❌ 误判。**连点两次即可稳定触发**，间隔约 1.5s 有效。之前失败是时序问题，与点击位置无关。 |
| 「次数 3次」是全局次数 | ❌ 错。顶部「次数」是**当前选中分类的剩余次数**；每个分类各自独立计数（实测同一天内通商护航/军备科技各 3 次、战场探索仅 1 次）。 |
| 共 6 个分类，最后一个在最右 | ✅ 对。第 6 类「战场探索」在初始状态下被屏幕右缘裁掉约 89px，**必须在卡片行内向左滑动**（约 `(1150,615)→(480,615)`，步长吸附 139px）才能完整露出。 |

**补充实测要点**

- `tab_daily.png` 是**未选中态**，在目标页只有 0.53 分；页面判据需另用「选中态」素材（`tab_daily_on.png`）。
- 已耗尽次数的分类：连点两次**不弹任何框**，此时应视为「跳过」，不能等待弹窗。
- 「获得奖励」横幅可直接复用 `image/task_claim/reward_popup.png`（实测 0.988）；`image/gift_claim/gift_reward_popup.png` 亦可（0.990）。
- 点击「点击继续」用固定点 `(1050,500)` 更稳：该点在结算层内可关闭，在日常页上是纯背景、误点无害。

---

## 一、项目背景与技术底座

### 1.1 项目

| 项 | 值 |
|---|---|
| 仓库路径 | `E:\DSH\MaaFX\MaaFXSLZK` |
| 项目名 | MaaFXSLZK（《拂晓：胜利之刻》日常自动化助手） |
| 分支 / 远端 | `main` → `origin/main`（GitHub: haoye3030/MaaFXSLZK） |
| 框架 | MaaFramework **v5.16.0-beta.2** + Python 绑定（`maa` 包） |
| 控制端 | 安卓端 ADB |
| ADB 路径 | `C:\Program Files\Netease\MuMu\nx_main\adb.exe` |
| 设备地址 | `127.0.0.1:16384`（MuMu 模拟器，另有 `emulator-5554`） |
| 分辨率 | 逻辑 **1280×720**（所有 ROI 坐标基准） |

### 1.2 目录结构

```
MaaFXSLZK/
├── assets/
│   ├── interface.json              ← 任务清单（每个功能一个 entry）
│   └── resource/
│       ├── pipeline/               ← 各功能流程定义（*.json）
│       └── image/<功能名>/          ← 模板素材
├── docs/zh_cn/develop/
│   ├── asset_guideline.md          ← 【必读】素材制作规范 + MAA 机制 + 坑清单
│   └── todo.md                     ← 17 项待做功能清单
└── tools/                          ← validate_schema.py 等官方脚本
```

### 1.3 已实现功能（5 个，均已实机验证）

| 功能 | pipeline | entry 节点 | 状态 |
|---|---|---|---|
| 领取任务奖励 | `task_claim.json` | `TaskClaimStart` | ✅ |
| 领取免费礼包 | `gift_claim.json` | `GiftClaimStart` | ✅ |
| 与秘书舰互动 | `secretary_talk.json` | `SecretaryTalkStart` | ✅ |
| 收取港区资源并换班 | `naval.json` | `NavalStart` | ✅ |
| 参与演习 | `exercise.json` | `ExerciseStart` | ⚠️ 仅验证了「刷新次数=0」分支 |

### 1.4 公共归位机制（已实现，5 个功能共用）

文件：`assets/resource/pipeline/navi.json`

```
NaviCommon (DirectHit, timeout 120000)
  ├─ NaviPopupCancel  命中「取消」按钮 → 点掉 → 回 NaviCommon
  ├─ NaviOnMain       命中主界面标志 → next=[{"name":"Resume","anchor":true}] → 跳回功能续跑
  ├─ NaviSubpage      命中左上 🏠 → 点它 → 回 NaviCommon
  └─ NaviWait         其余状态 → 等 2 秒 → 回 NaviCommon
```

每个功能入口 3 节点：

```json
"XxxStart": {
    "recognition": "DirectHit",
    "action": "DoNothing",
    "timeout": 120000,
    "anchor": { "Resume": "XxxResume" },
    "next": ["XxxNaviTarget", "NaviCommon"]
},
"XxxNaviTarget": {              // 已在目标页 → 直接执行
    "recognition": "TemplateMatch", "template": "...", "roi": [...],
    "action": "DoNothing", "timeout": 2000,
    "next": ["<任务流第一步>"]
},
"XxxResume": {                 // 归位完成后从这里续跑
    "recognition": "DirectHit",
    "action": "DoNothing",
    "next": ["<任务流第一步>"]
}
```

公共素材：
- `image/common/ui_main.png` — 主界面标志（底部「商店」按钮），ROI `[10,650,90,60]`
- `image/common/ui_subpage_home.png` — 子页面标志（左上 🏠），ROI `[185,10,110,60]`
- `image/common/ui_popup_cancel.png` — 系统弹窗「取消」按钮，ROI `[530,430,220,62]`

---

## 二、MaaFramework 关键机制（**实测得出，官方文档未写明**）

> 这些是实现本功能必须知道的规则，已同步写入 `asset_guideline.md`。

| # | 机制 | 实测结论 |
|---|---|---|
| 1 | **`next` 列表的执行时机** | **只在当前节点「识别成功」后才被遍历**。识别失败（超时）→ 直接走 `on_error`；无 `on_error` → 任务失败 |
| 2 | 推论 | 想做多分支，**当前节点必须用 `DirectHit` 保证成功**，把判断下沉到 next 列表里的具体节点 |
| 3 | **`anchor`** | `"anchor": {"Go": "TargetNode"}` 把锚点 `Go` 设为指定节点；`next`/`on_error` 中用 `{"name":"Go","anchor":true}` 引用 |
| 4 | **`jump_back: true`** | 写在 next 项上：执行完回到**父节点**的 next 列表，从本项之后继续 |
| 5 | **`inverse: true`** | 反转识别结果（匹配到=未识别）。配合 `on_error` 可判断「不在某状态」。注意：触发 `on_error` 需等该节点 timeout 耗尽 |
| 6 | **`timeout`** | 默认 20000ms；`-1` = 无限。**超时预算沿 next 链传递** —— 入口 timeout 太短会掐断下游的 `on_error` |
| 7 | **`DirectHit` 节点不生成调试图** | 判断节点是否执行要看 `maafw.log` 的 `node done`，不要只看 `debug/vision/` 的图 |
| 8 | **`DirectHit` 动作不会失败** | 点击被弹窗遮挡时仍报成功 → 关键动作后应加「结果校验」节点 |
| 9 | **纯色模板是假阳性源** | 纯色区域匹配任何纯色都是 1.0 分。素材必须标准差 > 15 |
| 10 | **重复键** | MAA 报 `load_all_json failed`，但 Python `json.loads` 静默通过 → 必跑 `maa-tools check` |

---

## 三、待实现功能：自动扫荡日常关卡

### 3.1 风险等级修正：🟢（无资源消耗）

**[实测]** 扫荡确认弹窗内的红色注意文字明确写着：

> 注意：扫荡只用于快速获取日常奖励，**不消耗燃料**，也不会增加经验和好感度。

扫荡只消耗**每日扫荡次数**（每天 3 次 / 关卡分类）。因此**不涉及钻石/体力等资源消耗**，
无需消耗上限控制。`todo.md` 中原标记为 🟡，实现完成后应改为 🟢。

### 3.2 完整 UI 流程

```
主界面
 └─ 点「出击」                       (1150, 565)
     └─ 点左侧「日常 DAILY ROUTINE」  ROI [86, 208, 88, 44]，中心 ≈ (130, 230)
         └─ 【日常关卡页】底部横排「关卡分类卡片」
             ├─ 周日,一,五 开放🔒
             ├─ 通商护航   3次   ROI [288, 595, 168, 91]
             ├─ 武器运输   3次   ROI [238, 595, 170, 92]   ← 🔒 未开放
             ├─ 综合演练   3次   ROI [621, 594, 168, 93]
             ├─ 军备科技   3次   ROI [810, 594, 170, 93]
             ├─ 战术演练   3次   ROI [1002, 595, 169, 92]
             └─ 战场探索   3次   ROI [1052, 595, 168, 92]
                  ↓
             第一次点某张卡片 → 选中该分类（卡片下方浮出青色「快速扫荡」按钮）
                  ↓
             再次点同一张卡片 → 触发扫荡
                  ↓
             弹出「确定扫荡 3 次?」 → 点「确定」
                  ↓
             完成 → 「获得奖励 REWARDS」结算层 → 点「点击继续」→ 回到日常页
```

**[口述]** 用户原话：
> 「点击图标就可以扫荡」「不用使用快速扫荡按钮，点选中关卡分类后可以多点一次来扫荡」
> 「多一次不是按钮。比如说第一次点击综合演练图标选中这个分类，再次点击综合演练图标进行快速扫荡」

**[实测]** 我的探查结果（存在出入，需实现时以实测为准）：

| 操作 | 结果 |
|---|---|
| 第 1 次点「综合演练」卡片 (705, 640) | 选中，卡片下方出现青色「快速扫荡」按钮 |
| 第 2 次点同一张卡片（间隔 4 秒） | **未弹窗**，画面不变 |
| 第 3 次点同一张卡片 | **弹出「确定扫荡 3 次?」** |
| 点青色「快速扫荡」按钮 (700, 660) | **必定弹出「确定扫荡 3 次?」** ✅ |
| 点「确定」(832, 461) | 扫荡执行 → 弹「获得奖励」结算 → 点「点击继续」→ **回到日常页**（⚠️ 原文「进入编队页」已证伪，见顶部修正） |

**[实测修正]** 连点两次**稳定可用**（间隔约 1.5s）。此前记录的「第 2 次无效」是点击时序/位置问题，不是机制。
实现时建议**先复现用户的「点两次」路径并确认**，若不稳定则回退到「点卡片 → 识别并点击『快速扫荡』按钮」方案
（后者位置浮动，需用 TemplateMatch 定位，不能写死坐标）。

### 3.3 界面元素精确坐标（**[实测]**，基于 1280×720）

#### A. 扫荡确认弹窗（「确定扫荡 3 次?」）

| 元素 | 范围 (x, y, w, h) | 备注 |
|---|---|---|
| 标题「确定扫荡 3 次?」 | `[572, 282, 133, 23]` | 弹窗**顶部** |
| 红色注意文字 | `[352, 335, 577, 63]` | 「注意：扫荡只用于快速获取日常奖励，不消耗燃料…」 |
| 「取消」按钮（灰） | `[539, 436, 183, 44]` | |
| **「确定」按钮（青）** | `[739, 436, 186, 51]` | 中心 ≈ (832, 461) |

#### B. 「未开放」弹窗（点🔒关卡时出现）

| 元素 | 范围 | 备注 |
|---|---|---|
| 标题文字 | `[532, 318, 214, 39]` | |
| 「确定」按钮（青） | `[738, 436, 186, 49]` | 与 A 的确定按钮位置几乎一致，**可共用同一素材** |

#### C. 关卡编队页（⚠️ 本流程不会进入，仅为存档）

> [实测修正] 扫荡的「确定」不是进入编队页，而是直接结算并回日常页。以下坐标仅在该页被其他功能用到时才需要。

| 元素 | 范围 / 位置 | 备注 |
|---|---|---|
| 「扫荡」蓝色按钮 | ≈ (800, 571) | x≈757~843, y≈543~600 |
| 「多倍战斗 1 ▲▼」选择器 | x≈900~1129, y≈493~529 | ▲/▼ 可调倍数 |
| 「TEAM 01」编队槽位 | 约 6 格 | 出战舰娘 LV.93 ×2 |

#### D. 顶部「次数 3次」选择器

| 元素 | 范围 |
|---|---|
| 「次数」文字 | x≈364~436, y≈60~95 |
| 「3次」黑色框 | x≈443~586, y≈55~95 |

**[实测修正]** 该数字是**当前选中分类的剩余次数**，不可点击，也没有下拉菜单。每个分类各自独立（同一天内可分别为 3/3/1 次）。

---

### 3.4 已有素材（用户提供，位于 `assets/resource/image/exercise/_raw/`）

⚠️ **所有弹窗文字素材都是拖影**（MAA 扩展截图抓在弹窗淡入动画中间帧），**不可直接使用**。
卡片类素材（建筑图 + 关卡名 + 次数）是清晰的，**可用**。

| 文件名（去 ROI 后缀） | 尺寸 | 可用性 |
|---|---|---|
| `出击_日常` | 88×44 | ✅ 清晰 —— 左侧「日常」标签 |
| `出击_日常_通商护航_已开放` | 168×91 | ✅ |
| `出击_日常_武器运输_未开放` | 170×92 | ✅（🔒 样式） |
| `出击_日常_综合演练_已开放` | 168×93 | ✅ |
| `出击_日常_军备科技_已开放` | 170×93 | ✅ |
| `出击_日常_战术演练_已开放` | 169×92 | ✅ |
| `出击_日常_战场探索_已开放` | 168×92 | ✅ |
| `出击_日常_扫荡_已开放_提示` (577×63) | — | ❌ 拖影 |
| `出击_日常_扫荡_已开放_提示` (214×39) | — | ❌ 拖影 |
| `出击_日常_扫荡_已开放_确定按钮` | 186×51 | ✅ 清晰（青色确定按钮） |
| `出击_日常_武器运输_未开放_提示` | 214×39 | ❌ 拖影 |
| `出击_日常_武器运输_未开放_确定按钮` | 186×49 | ✅ 清晰 |

**素材命名沿用规范**：`<用途>_<描述>.png`，放在 `assets/resource/image/<功能名>/`。

**建议做法**：弹窗文字素材由实现者**自行用 ADB 截取**（`adb exec-out screencap -p`），
等弹窗完全稳定后截，避免拖影。

---

### 3.5 实现建议

#### 流程结构（pipeline）

```
DailySweepStart (DirectHit, anchor {Resume: DailySweepResume}, timeout 120000)
  ├─ DailySweepNaviTarget  ← 已在日常关卡页 → 直接继续
  └─ NaviCommon            ← 否则先归位到主界面

DailySweepResume
  └─ DailySweepEnterBattle    点「出击」(1150,565)
      └─ DailySweepClickDaily  点左侧「日常」(130,230)
          └─ DailySweepSelectCard   点某个关卡分类卡片
              └─ DailySweepTrigger    再次点同一张卡 / 或点「快速扫荡」
                  └─ DailySweepConfirm  识别「确定扫荡 N 次?」→ 点确定 (832,461)
                      └─ DailySweepLoop    回 DailySweepSelectCard 扫下一个分类
```

#### 关键决策点（需实现时确定）

1. **扫哪些关卡分类？**
   - 固定扫全部「已开放」的分类（需跳过🔒的「武器运输」）
   - 或用 `interface.json` 的 `option` 让用户选（MAA 原生支持下拉框）
   - **推荐**：先用 OCR 读卡片文字判断「是否开放」，或者用「未开放弹窗」作为排除依据
2. **扫几次？**
   - 每个分类扫 1 次（用完 3 次额度后跳过）
   - 或扫到次数用完
   - **推荐**：扫 1 次即可（日常任务通常只要求参与若干次），用完后再点会弹「次数已用尽」
3. **怎么排除🔒未开放的分类？**
   - **推荐**：点卡片后若弹出「未开放」弹窗 → 点确定 → 跳过该分类（识别弹窗标题文字）
   - 或直接用固定坐标跳过已知🔒位置（不通用，账号不同🔒位置可能不同）
4. **扫荡完成后停在哪个页面？**
   - **[实测，已修正]** 停在「获得奖励」结算层，点「点击继续」后**直接回到日常页**，滚动位置保持。
     全程不经过编队页，**不需要返回键、也不需要归位重进**。
   - 若回到日常页需要重新点卡片，会再次触发扫荡 → **必须有「次数已用尽」的状态判据来终止循环**

#### 终止条件（重要）

**[实测修正]** 次数用完后连点两次**不弹任何提示框**，界面无变化。
因此判据不需要具体文案：**识别不到扫荡确认框 = 该分类不可扫 = 跳过**。
pipeline 必须能识别它并终止循环，否则会无限循环。

建议用 `max_hit` 兜底 + 「次数」显示识别（顶部「次数 3次」→ 扫完变「0次」）。

---

## 四、通用工作流程（每个新功能都适用）

### 4.1 探查阶段

```bash
cd C:\Users\alex2\WorkBuddy\2026-11-06-18-49-59
python - <<'PYEOF'
import sys, time; sys.path.insert(0,"tools")
import nav
nav.connect()
ok,_ = nav.to_home(); print("回主界面:", ok)
nav.tap(X, Y); time.sleep(6)
nav.grab("probe.png")     # 存到 adb_shots/
PYEOF
```

`tools/nav.py` 提供：`connect()` / `grab(name)` / `classify(png)` / `tap(x,y)` / `back(n)` / `to_home()`。
`classify()` 返回 `home` / `subpage` / `gacha` / `loading` / `unknown`。

> ⚠️ `nav.py` 的 `COORDS` 是老号坐标，与新号不同。**不要依赖它做定位**，用实测坐标。

### 4.2 素材制作（详见 `asset_guideline.md`）

三项必做校验：
1. **标准差 > 15**（防纯色假阳性）：`np.asarray(Image.open(p).convert("RGB")).astype(int).std()`
2. **目标位置 NCC ≥ 0.9**
3. **干扰位置 NCC 明显低于目标**（余量越大越稳）

选素材范围的判据：**该元素周围是否有外观相似的同类？**
- 有并列同类（如底部 8 个导航按钮）→ 只截独特部分（文字）
- 元素本身独特 → 可截整块

### 4.3 调试

```python
from maa.tasker import Tasker
Tasker.set_log_dir(r"E:\DSH\MaaFX\MaaFXSLZK\debug")
Tasker.set_save_draw(True)     # ← 唯一正确的开启方式（写 config/maa_option.json 无效）
```

- 调试图 → `debug/vision/{节点名}_{reco_id}_{时间戳}.jpg`（画面上画 ROI 框 + 命中位置）
- 实际得分 → `debug/maafw.log`，搜 `TemplateMatcher.cpp ... analyze`，形如
  `ExerciseTrust [all_results_=[{"box":[829,670,153,44],"score":0.999741}]]`
- **DirectHit 节点不产图**，看 `node done` 判断是否执行

### 4.4 静态校验（提交前必做）

```powershell
cd E:\DSH\MaaFX\MaaFXSLZK
python tools/validate_schema.py --schema-dir deps/tools --resource-dirs assets/resource `
    --exclude-dirs assets/resource/announcement --interface-files assets/interface.json
npx @nekosu/maa-tools check
```

### 4.5 接入 interface.json

```json
{
    "name": "自动扫荡日常关卡",
    "label": "自动扫荡日常关卡（未测试）",
    "entry": "DailySweepStart",
    "description": "⚠️ **尚未完整测试**...\n\n自动进入出击→日常，对已开放的关卡分类逐个扫荡。扫荡不消耗燃料，仅消耗每日扫荡次数。"
}
```

`interface.json` 是 **JSONC**（带行注释），解析要用 `tools/validate_schema.py` 的 `load_jsonc()`。

### 4.6 提交

```powershell
cd E:\DSH\MaaFX\MaaFXSLZK
git add -A
git status
git commit -m "feat: add daily sweep pipeline"
git push
```

> CRLF 警告是正常的（仓库历史一直是 CRLF，`.gitattributes` 的 `eol=lf` 未生效但无害）。
> JSON 解析器容忍 CRLF，CI 在 Linux 上跑没问题。

---

## 五、已知坑清单（速查）

| 坑 | 表现 | 解决 |
|---|---|---|
| 裁到纯色区域 | 模板在任意纯色处都 1.0 分，假阳性 | 标准差 > 15 校验 |
| 小图标做模板 | 同类深色小图标互相误匹配 | 改用文字等独特特征 |
| 弹窗遮罩 | 底层界面仍部分可见 → 归位判定通过但点击被挡 → **假成功** | 归位流程加弹窗关闭节点 |
| DirectHit 动作 | 不会失败，点击被挡也报成功 | 关键动作后加结果校验 |
| next 列表 | 识别失败时**不会**遍历 next | 当前节点用 DirectHit 保证成功 |
| timeout 传递 | 入口 timeout 短 → 下游 on_error 来不及触发 | 入口给足预算（120000） |
| DirectHit 无调试图 | 误判节点没执行 | 查日志 `node done` |
| JSON 重复键 | MAA 报错但 Python 静默通过 | 必跑 `maa-tools check` |
| 素材拖影 | MAA 扩展截图抓在动画中间帧 | 等弹窗稳定后再截，或用 ADB screencap |
| 老号/新号坐标不同 | 同一功能在新号失效 | 用 TemplateMatch 识别，别写死坐标 |

---

## 六、参考资料

| 文档 | 地址 |
|---|---|
| 本项目素材规范（含 MAA 机制详解） | `docs/zh_cn/develop/asset_guideline.md` |
| 本项目待做功能清单（17 项） | `docs/zh_cn/develop/todo.md` |
| MAA 官方文档（任务流水线协议） | https://maafw.com/docs/3.1-Task-Pipeline-Protocol/ |
| MAA VS Code 扩展（Maa Pipeline Support） | https://docs.maa.plus/zh-cn/develop/vsc-ext-tutorial.html |
| MAAFramework 源码 | https://github.com/MaaXYZ/MaaFramework |

### MAA VS Code 扩展用法（截图调试必备）

扩展 ID `maa-support`，显示名 **Maa Pipeline Support**。

- `Ctrl+Shift+P` → `Maa: 打开截图工具`
- 连控制器 → 「截图」取原始 1280×720 画面
- `Ctrl` + 拖拽框选；滚轮缩放
- 「下载」保存到资源目录；**「复制」把 ROI 以 `[x,y,w,h]` 复制到剪贴板**（坐标按 1280×720 自动缩放）
- 「工具」→ 对当前图直接测模板匹配/OCR 得分
- `Maa: 打开 maa 日志` → 看 `maafw.log`
