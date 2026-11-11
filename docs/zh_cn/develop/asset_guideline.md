# 素材制作规范

本文档记录 MaaFXSLZK 项目中图像素材（TemplateMatch 模板）的制作方法与验证流程。

## 一、核心原则

模板匹配（MaaFramework 的 TemplateMatch）用的是 **NCC 归一化互相关**，衡量的是"图案形状是否一致"，与颜色、明暗无关。

素材质量的目标不是"像素多"，而是 **保留该元素最具区分度的特征，同时排除与干扰元素共有的特征**。

## 二、截取范围的选择

判断依据：**这个元素周围是否存在外观相似的同类元素？**

| 情况 | 截取策略 | 例子 |
|---|---|---|
| 存在并列的同类元素 | **只截独特部分**（文字/图标） | 主界面底部 8 个导航按钮（仓库/船坞/港区/建造/任务/图鉴/排行/商店）外观几乎相同，必须只截文字 |
| 元素本身样式独特 | **可截整块** | 「快速领取」深色描边按钮、「邮件」小信封图标 |
| 独立弹窗标题 | **截文字行**，范围紧凑但笔画完整 | 「演习连续挑战结束」「确认更新演习对手吗?」 |
| 数字/状态标记 | **截到最紧** | 刷新次数分子 `1`/`2`、全选框的勾 |
| 无并列但样式普通 | 截文字或图标，避开大面积背景 | — |

### 反面案例

- ❌ 截了整块按钮（149×50，含背景+图标+文字）→ 在 8 个并列按钮间区分度从 0.90 降到 0.23
- ❌ 截到了纯色区域（一片灰/一片黑）→ **纯色模板匹配任何纯色区域都是 1.0 分**，会产生假阳性

## 三、截完必须做的三项校验

任何新素材在提交前必须通过：

### 1. 非纯色检查（防假阳性）

```python
import numpy as np
from PIL import Image
a = np.asarray(Image.open("素材.png").convert("RGB")).astype(int)
assert a.std() > 15, f"纯色废片！标准差 {a.std():.1f}"
```

标准差 < 15 视为废片。本项目曾一次性出现 3 张纯色废片（标准差 3.6~6.5），
其中 `popup_end_title.png` 导致 `ExerciseWaitEnd` 节点在**战斗画面**上假阳性通过，
流程提前跳到下一步而错过真正的结束弹窗。

### 2. 目标位置得分

模板在**目标 ROI** 内的最佳 NCC 应 ≥ 0.9（越接近 1.0 越好，阈值通常设 0.7）。

### 3. 干扰位置得分（关键）

模板在**外观相似的干扰位置**上的 NCC 必须明显低于目标位置。

以「任务」按钮为例（8 个并列导航按钮）：

| 素材 | 商店 | 船坞 | 仓库 | 港区 | 建造 | **任务** | 图鉴 | 排行 | 余量 |
|---|---|---|---|---|---|---|---|---|---|
| 只截文字 | 0.003 | 0.070 | 0.089 | 0.019 | 0.062 | **0.996** | 0.090 | 0.026 | **0.91** |
| 整块按钮 | 0.496 | 0.508 | 0.502 | 0.454 | 0.465 | **0.784** | 0.515 | 0.551 | 0.23 |

只截文字的余量是整块的 4 倍，抗干扰能力显著更强。

## 四、推荐工具

### VS Code 扩展「Maa Pipeline Support」

扩展 ID `maa-support`，显示名 **Maa Pipeline Support**。核心能力：

- **截图工具**：`Ctrl+Shift+P` → `Maa: 打开截图工具`
  - 连接控制器后点「截图」→ 直接抓取 1280×720 原始画面（无缩放问题）
  - `Ctrl` + 拖拽框选，滚轮缩放
  - 「下载」自动保存到资源目录并命名，可直接被 `template` 引用
  - 「复制」把 ROI 以 `[x, y, w, h]` 数组复制到剪贴板，直接粘进 `roi` 字段
    （**坐标按 1280×720 基准自动缩放**）
- **快速识别**：对当前截图直接测模板匹配/OCR 得分
- **日志**：`Maa: 打开 maa 日志` 查看 `maafw.log`

### 调试可视化（Python 侧）

```python
from maa.tasker import Tasker
Tasker.set_log_dir(r"E:\DSH\MaaFX\MaaFXSLZK\debug")
Tasker.set_save_draw(True)     # ← 正确的开启方式
```

- 调试图输出到 `<log_dir>/vision/`，文件名 `{节点名}_{reco_id}_{时间戳}.jpg`
- 画面上会画出 ROI 框、命中位置和匹配分数，右侧有模板对照
- ⚠️ 写进 `config/maa_option.json` 无效，必须用 API 或
  `Toolkit.init_option(path, {"save_draw": True})`

### 从日志读实际得分

`debug/maafw.log` 里每个节点的模板匹配得分：

```
[TemplateMatcher.cpp][L45][...] ExerciseTrust [all_results_=[{"box":[829,670,153,44],"score":0.999741}]]
```

调阈值时这是最权威的依据，比反复试跑高效得多。

## 五、命名约定

| 目录 | 用途 |
|---|---|
| `assets/resource/image/<功能>/` | 各功能自己的素材 |
| `assets/resource/image/common/` | 主界面通用入口素材（跨功能复用） |

命名用 `用途_描述.png`，例如：

- `nav_shop.png` — 主界面「商店」导航
- `btn_attack.png` — 「出击」按钮
- `btn_quick_claim.png` — 「快速领取」
- `popup_ok.png` — 弹窗「确定」
- `chk_on.png` — 复选框勾选态
- `num_1.png` — 数字 1

## 六、Pipeline 配置要点

### next 列表的执行规则（实测，务必理解）

**`next` 列表只在当前节点「识别成功」后才会被遍历。**

- 识别成功 → 依次尝试 next 列表，命中第一个识别成功的节点
- 识别失败（超时）→ **不会遍历 next**，直接走 `on_error`；若没有 `on_error` 则任务失败

这带来两个推论：

1. 想用 `next` 做「多分支」，当前节点必须**保证能识别成功**（用 `DirectHit`），把判断下沉到 next 列表里的具体节点
2. 想在「识别失败时做别的事」，用 `on_error`，而不是指望 next 列表

### 公共前置 + 跳回调用方

多个功能共享「自动归位到主界面」这类前置逻辑时，用 `anchor` 实现，避免每个功能复制一遍：

```json
// navi.json —— 公共归位（全局节点空间，各 pipeline 共用）
{
    "NaviCommon": {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "timeout": 120000,
        "next": ["NaviOnMain", "NaviSubpage", "NaviWait"]
    },
    "NaviOnMain": {
        "recognition": "TemplateMatch",
        "template": "common/ui_main.png",
        "roi": [10, 650, 90, 60],
        "threshold": 0.7,
        "action": "DoNothing",
        "timeout": 2000,
        "next": [{ "name": "Resume", "anchor": true }]
    },
    "NaviSubpage": {
        "recognition": "TemplateMatch",
        "template": "common/ui_subpage_home.png",
        "roi": [185, 10, 110, 60],
        "threshold": 0.7,
        "action": "Click",
        "post_delay": 2500,
        "timeout": 2000,
        "max_hit": 8,
        "next": ["NaviCommon"]
    },
    "NaviWait": {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "post_delay": 2000,
        "timeout": 2000,
        "next": ["NaviCommon"]
    }
}
```

```json
// 各功能自己的 pipeline
{
    "TaskClaimStart": {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "timeout": 120000,
        "anchor": { "Resume": "TaskClaimResume" },     ← 设置锚点，指向续跑节点
        "next": ["TaskClaimNaviTarget", "NaviCommon"]
    },
    "TaskClaimNaviTarget": {                          ← 已在本功能的目标页 → 直接执行
        "recognition": "TemplateMatch",
        "template": "task_claim/task_tab_all.png",
        "roi": [30, 105, 225, 85],
        "threshold": 0.7,
        "action": "DoNothing",
        "timeout": 2000,
        "next": ["TaskClaimClickAll"]
    },
    "TaskClaimResume": {                             ← 归位完成后从这里续跑
        "recognition": "DirectHit",
        "action": "DoNothing",
        "next": ["TaskClaimClickTask"]
    }
}
```

`anchor` 相关语法：

| 写法 | 含义 |
|---|---|
| `"anchor": "MyAnchor"` | 把锚点 `MyAnchor` 设为当前节点 |
| `"anchor": { "Go": "TargetNode" }` | 把锚点 `Go` 设为指定节点 `TargetNode` |
| `{ "name": "Resume", "anchor": true }` | 引用锚点 `Resume`（在 `next` / `on_error` 中） |

### inverse：把「识别到」当成「没识别到」

适合「不在某状态时」的判断，配合 `on_error` 使用：

```json
{
    "NaviCheck": {
        "recognition": "TemplateMatch",
        "template": "common/ui_main.png",
        "inverse": true,                  ← 在主界面时视为"未识别"
        "timeout": 6000,
        "on_error": ["SomeNode"],         ← 匹配成功（即在主界面）→ 走这里
        "next": ["OtherNode"]             ← 匹配失败（即不在主界面）→ 走这里
    }
}
```

⚠️ 用 `inverse` + `on_error` 时注意：节点必须**等自己的 timeout 耗尽**才会触发 `on_error`，
所以这个节点的 timeout 就是等待时长，别设太大。

### jump_back：执行完跳回父节点的 next 列表

`next` 里的 `{ "name": "X", "jump_back": true }` 表示：X 执行完成后，跳回**父节点**的
next 列表，从 X 之后的那一项继续。

### timeout 要沿链传递

`timeout` 默认 20000ms，且**上游节点 timeout 太短会先耗尽，导致下游的 `on_error` 来不及触发**。

```json
"ExerciseStart": {
    "timeout": 120000,          ← 入口给足预算，否则归位流程会被提前掐断
    "next": ["ExerciseNaviTarget", "NaviCommon"]
}
```

### next 列表要设计成收敛的

MAA 在 next 全部失败时会回退到父节点的 next 列表继续尝试。
链路上应提供 `DirectHit` 兜底节点，避免无限回退：

```json
"ExerciseEndNow": {
    "recognition": "DirectHit",
    "action": "DoNothing",
    "next": ["ExerciseBackHome"]
}
```

### 改完必须跑校验

```powershell
cd E:\DSH\MaaFX\MaaFXSLZK
python tools/validate_schema.py --schema-dir deps/tools --resource-dirs assets/resource `
    --exclude-dirs assets/resource/announcement --interface-files assets/interface.json
npx @nekosu/maa-tools check
```

⚠️ **JSON 重复键 MAA 会报 `load_all_json failed`，但 Python 的 `json.loads` 会静默通过** ——
所以 `maa-tools check` 不能跳过。

## 七、已知的坑清单

| 坑 | 表现 | 解决 |
|---|---|---|
| 裁到纯色区域 | 模板在任意纯色处都 1.0 分，假阳性 | 标准差 > 15 校验 |
| 小图标模板 | 左侧 6 个深色模式图标互相误匹配 | 改用英文单词「EXERCISE」，区分度 56~116 |
| 弹窗遮罩 | 截图时弹窗未完全弹出，标题被遮罩吞掉 | 等弹窗完全稳定再截 |
| 坐标估算 | 看图估算点击位置，偏差 60+ 像素 | 用 MAA 扩展「复制」拿精确 ROI |
| 脚本硬编码探查 | 在非主界面时点击，误判为账号差异 | 探查前先确认当前页面状态 |
| **DirectHit 不生成调试图** | 误以为节点没执行 | 查 `maafw.log` 的 `node done` 而非调试图 |
| **next 列表只在识别成功时遍历** | 识别失败时 next 里的节点全都没跑 | 当前节点用 `DirectHit` 保证成功，把判断下沉 |
| **inverse 触发 on_error 需等 timeout** | 等待时间不可控 | 调小该节点 timeout |
