<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://cdn.jsdelivr.net/gh/MaaAssistantArknights/design@main/v1/icons/maa-logo_512x512.png" width="256" height="256" />
</p>

<div align="center">

# MaaFXSLZK

**《拂晓：胜利之刻》自动化助手**

</div>

<p align="center">
  <a href="https://github.com/haoye3030/MaaFXSLZK/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/haoye3030/MaaFXSLZK?style=flat-square" /></a>
  <a href="https://github.com/haoye3030/MaaFXSLZK/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/haoye3030/MaaFXSLZK?style=flat-square" /></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-Android-blueviolet?style=flat-square" />
</p>

---

## 简介

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发的《拂晓：胜利之刻》日常自动化助手。

通过图像识别与模拟控制，帮助玩家完成重复的日常操作。

> ⚠️ **本项目处于早期开发阶段（v0.1.0），功能尚未完善，欢迎issue 反馈问题。**

## 特性

- ✅ **领取任务奖励** —— 自动进入任务页，一键领取已完成任务的奖励，完成后返回主界面
- ✅ **领取免费礼包** —— 领取商店每日/每周礼包的免费项，已领取时自动跳过，不触碰付费商品
- ✅ **与秘书舰互动** —— 点击主界面中央的秘书舰 3 次，完成每日任务
- ✅ **参与演习** —— 自动演习并托管战斗，打满当日刷新次数，刷新为 0 时不再换对手
- ✅ **收取港区资源并换班** —— 收取炼油厂/便利店资源并为两处设施重新排班
- ⚠️ **自动扫荡日常关卡** —— 出击 → 日常，对已开放分类逐个扫荡，次数用尽的分类自动跳过（**尚未完整测试**，谨慎使用）
- ⚠️ **自动合成仓库道具** —— 按类别（训练材料 / 食物 / 箱子）勾选，把该类素材逐个合到上限（**尚未完整测试**，且**合成不可撤销**，谨慎使用）
- ⚠️ **自动兑换补给商店** —— 按类别（食物 / 部件 / 6 种特训科目）勾选购买，支持滚动查找第三排（**尚未完整测试**，购买消耗货币且不可撤销）
- ⚠️ **领取临期邮件** —— 按「即将过期」排序，只领取剩余天数在阈值内的邮件附件，可配置 1/3/7 天（**尚未完整测试**）

## 环境要求

| 项目 | 要求 |
| :--- | :--- |
| 分辨率 | **1280 × 720（横屏）**，短边须为 720 |
| 设备 | Android 模拟器或真机（需开启 ADB 调试） |
| 控制方式 | ADB |
| 运行环境 | Windows / macOS / Linux（需 MaaFramework 运行环境） |

**推荐的模拟器**：MuMu 模拟器、雷电模拟器等，测试环境为 MuMu 模拟器。

## 使用方法

> ⚠️ **运行前请先回到主界面**
>
> 所有任务都从主界面开始识别。启动前请确认：
>
> - 游戏停在**主界面**（底部能看到商店 / 船坞 / 仓库 / 港区 / 建造 / 任务 / 图鉴 / 排行）
> - 已关闭**所有遮罩弹窗**，包括每日 00:00 刷新后自动弹出的「连续登录补给」签到框
> - 不在商店、船坞、任务页等任何子页面
>
> 若停留在子页面或弹窗上，第一步模板匹配会超时失败。
> 任务执行完毕后会自动返回主界面。

### 方式一：使用 MaaPiCli（命令行）

```bash
# 首次使用需先登录并配置设备
maapicli device -a 127.0.0.1:16384

# 运行任务
maapicli run --task <任务名>
```

### 方式二：使用 GUI 客户端

社区提供了多个基于 MaaFramework 的 GUI 客户端（如 [MFAAvalonia](https://github.com/MaaAssistantArknights/MFAAvalonia)），可直接图形化操作。

## 开发

### 开发文档

- [素材制作规范](docs/zh_cn/develop/asset_guideline.md) —— 模板截取范围如何选择、截完如何校验、Pipeline 配置要点与已知坑清单
- [待完成功能清单](docs/zh_cn/develop/todo.md) —— 计划实现的 17 项功能，含风险分级与建议实施顺序
- [日常扫荡实现规格](docs/zh_cn/develop/daily_sweep_spec.md) —— 日常关卡扫荡的界面流程、坐标、判据与实测坑

### 从模板创建

本项目基于 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate) 创建。

```bash
gh repo create MaaFXSLZK --template MaaXYZ/MaaPracticeBoilerplate --public --clone
cd MaaFXSLZK
git submodule update --init --recursive
```

### 目录结构

```
MaaFXSLZK/
├── assets/                    # 资源层
│   ├── interface.json         #   应用入口：UI 显示与任务列表
│   └── resource/
│       ├── pipeline/          #   流程定义：识别 → 动作 → 跳转
│       └── image/             #   图像素材（模板匹配用）
├── agent/                     # 扩展层：Python 自定义识别与动作
├── docs/                      # 文档
└── tools/                     # 官方脚本（校验、打包）
```

### 本地校验

提交前请运行：

```bash
# 资源检查（需 Node.js）
npm ci
npx @nekosu/maa-tools check

# JSON Schema 校验（需 Python）
python -m pip install jsonschema==4.26.0 referencing==0.37.0
python tools/validate_schema.py \
  --schema-dir deps/tools \
  --resource-dirs assets/resource \
  --exclude-dirs assets/resource/announcement \
  --interface-files assets/interface.json
```

## 生态共建

MAA 正计划建设为一类项目，而非舟的单一软件。

若您的项目依赖于 MaaFramework，我们欢迎您将它命名为 MaaXXX、MXA、MAX 等等。当然，这是许可而不是限制，您也可以自由选择其他与 MAA 无关的名字，完全取决于您自己的想法。

欢迎向 [MaaFramework 社区项目列表](https://github.com/MaaXYZ/MaaFramework#%E7%A4%BE%E5%8C%BA%E9%A1%B9%E7%9B%AE) 提交 PR 添加您的项目！

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动！

感谢以下开发者对本项目所作的贡献：

[![Contributors](https://contrib.rocks/image?repo=haoye3030/MaaFXSLZK&max=1000)](https://github.com/haoye3030/MaaFXSLZK/graphs/contributors)

## 许可证

本项目采用 [MIT 许可证](./LICENSE) 开源。
