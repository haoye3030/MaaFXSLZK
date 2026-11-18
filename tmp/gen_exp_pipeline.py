# -*- coding: utf-8 -*-
"""生成新 expedition.json：远征派遣重构 v1（分组模式开）。
从旧文件复制保留节点、以旧行节点为模板生成 90 个行节点、
15 个限时 chip、15 个每日门控。幂等：重复跑时模板从新文件取。"""
import json, copy, shutil, sys

REPO = 'E:/DSH/MaaFX/MaaFXSLZK'
PIPE = REPO + '/assets/resource/pipeline/expedition.json'
BAK = 'E:/DSH/MaaFX/tmp/expedition.json.pre-rework'

with open(PIPE, encoding='utf-8') as f:
    old = json.load(f)

shutil.copyfile(PIPE, BAK)

KEEP = ['ExpeditionStart','ExpeditionResume','ExpOnMain','ExpOpenQuick','ExpEnterExpedition',
        'ExpWaitPage','ExpInExpedition','ExpClaimAll','ExpDismissReward','ExpClaimDone','ExpFullStop',
        'ExpPanelGuard','ExpPanelDispatched','ExpPanelGo','ExpAfterDispatch','ExpPanelRetry',
        'ExpCheckFull','ExpBackHome','ExpEnd','ExpDone','ExpScrollDown']

new = {}
for k in KEEP:
    assert k in old, f'missing keep node {k}'
    new[k] = copy.deepcopy(old[k])

MUT = {
    'ExpClaimDone':       {'next': ['ExpRePlan']},
    'ExpPanelGuard':      {'next': ['ExpRePlan']},
    'ExpPanelDispatched': {'next': ['ExpRePlan']},
    'ExpAfterDispatch':   {'next': ['ExpCheckFull', 'ExpRePlan']},
    'ExpCheckFull':       {'on_error': ['ExpRePlan']},
    'ExpScrollDown':      {'next': ['ExpDlyGateS8']},
    'ExpPanelGo':         {'on_error': ['ExpPanelFail']},
}
for k, m in MUT.items():
    for f, v in m.items():
        new[k][f] = copy.deepcopy(v)

# ---- 派遣面板兜底：沿用旧 ExpPanelFail / ExpPanelFail2 ----
# 实测：限时行与每日行的时长文本同为 HH:MM:SS（限时行下方另有一行倒计时），
# 所以「行时长仍可见 → 面板没弹出」这一判据两组通用，不需要拆两套。
src_fail  = old.get('ExpPanelFail')  or old.get('ExpPanelFailLtd')
src_fail2 = old.get('ExpPanelFail2') or old.get('ExpPanelFail2Ltd')
assert src_fail and src_fail2, 'panel fail nodes missing'

new['ExpPanelFail'] = copy.deepcopy(src_fail)
new['ExpPanelFail']['expected'] = r'.*\d{1,2}:00:00.*'
new['ExpPanelFail']['next'] = ['ExpPanelGo', 'ExpPanelFail2']
new['ExpPanelFail2'] = copy.deepcopy(src_fail2)
new['ExpPanelFail2']['next'] = ['ExpRePlan']

# ---- 中枢 + 夜窗门 ----
new['ExpRePlan'] = {
    'recognition': 'DirectHit', 'action': 'DoNothing', 'timeout': 6000, 'max_hit': 20,
    'next': ['ExpPanelGuard', 'ExpFullStop', 'ExpNightGate'], 'on_error': ['ExpBackHome']}
new['ExpNightGate'] = {
    'recognition': 'Custom', 'custom_recognition': 'ExpIsNightWindow',
    'custom_recognition_param': {'start': '18:00', 'end': '23:59'},
    'timeout': 3000, 'next': ['ExpLtdChipS12'], 'on_error': ['ExpDlyGateS8']}

# ---- 行节点模板（从旧行节点取字段形状） ----
and_tpl = old.get('ExpRow1Part3') or old.get('ExpLtdRowS12R1')
ocr_tpl = old.get('ExpRow1Any')  or old.get('ExpLtdRowC12R1')
assert and_tpl and ocr_tpl, 'row templates missing'
assert and_tpl.get('recognition') == 'And', 'ExpRow1Part3 not And'
assert ocr_tpl.get('recognition') == 'OCR', 'ExpRow1Any not OCR'

ROW_GEO = {
    1: {'text_y': 215, 'icon_y': 165, 'click': [878, 232]},
    2: {'text_y': 342, 'icon_y': 295, 'click': [880, 360]},
    3: {'text_y': 470, 'icon_y': 430, 'click': [887, 488]},
}
TIER_TPL = {
    'S': 'expedition/part3.png',
    'A': ['expedition/coconut.png', 'expedition/chicken.png',
          'expedition/basic_gear.png', 'expedition/high_gear.png'],
    'B': 'expedition/ge.png',
}
LTD_CHIP = {12: [1197, 655], 10: [1076, 655], 8: [946, 655]}
DLY_CHIP = {8: [1197, 604], 4: [1076, 604], 2: [946, 604]}
LTD_CHAIN = [('S',12),('S',10),('S',8), ('A',12),('A',10),('A',8),
             ('B',8),('B',10),('B',12), ('C',8),('C',10),('C',12),
             ('D',8),('D',10),('D',12)]
DLY_CHAIN = [('S',8),('S',4),('S',2), ('A',8),('A',4),('A',2),
             ('B',2),('B',4),('B',8), ('C',2),('C',4),('C',8),
             ('D',2),('D',4),('D',8)]
ROW_NEXT = ['ExpPanelDispatched', 'ExpPanelGo', 'ExpPanelFail', 'ExpPanelFail2']

def make_row(prefix, tier, dur, r, text):
    body = copy.deepcopy(and_tpl if tier in TIER_TPL else ocr_tpl)
    geo = ROW_GEO[r]
    if body.get('recognition') == 'And':
        for e in body['all_of']:
            if e['recognition'] == 'OCR':
                e['expected'] = text
                if 'roi' in e: e['roi'] = [825, geo['text_y'], 130, 40]
            elif e['recognition'] == 'TemplateMatch':
                e['template'] = copy.deepcopy(TIER_TPL[tier])
                if 'roi' in e: e['roi'] = [1170, geo['icon_y'], 95, 95]
    else:
        body['expected'] = text
        if 'roi' in body: body['roi'] = [825, geo['text_y'], 130, 40]
    body['action'] = 'Click'
    body['target'] = geo['click']
    body['post_delay'] = 1200
    body['timeout'] = 3000
    body['max_hit'] = 4
    body['next'] = list(ROW_NEXT)
    body.pop('on_error', None)
    name = f'{prefix}Row{tier}{dur}R{r}'
    new[name] = body
    return name

def make_chip(tier, dur, nxt):
    # timeout 默认 20000：实测一个无可派行的档位要空转 20s 才跳下一个档位，
    # 4 个档位失败就吃掉 80s+。这里显式压到 2400ms（post_delay 1200 + 2 轮重试），
    # rate_limit 600 让重试更密。DirectHit 点击永不失败，timeout 只约束 next 列表重试。
    x, y = LTD_CHIP[dur]
    name = f'ExpLtdChip{tier}{dur}'
    new[name] = {
        'recognition': 'DirectHit', 'action': 'Click', 'target': [x, y],
        'post_delay': 1200, 'timeout': 2400, 'rate_limit': 600,
        'next': [f'ExpLtdRow{tier}{dur}R1', f'ExpLtdRow{tier}{dur}R2', f'ExpLtdRow{tier}{dur}R3'],
        'on_error': [nxt]}
    return name

def make_gate(tier, dur, nxt):
    x, y = DLY_CHIP[dur]
    name = f'ExpDlyGate{tier}{dur}'
    new[name] = {
        'recognition': 'Custom', 'custom_recognition': 'ExpTimeCheck',
        'custom_recognition_param': {'latest_done': '23:00', 'duration_hours': dur},
        'action': 'Click', 'target': [x, y], 'post_delay': 1200, 'timeout': 3000,
        'next': [f'ExpDlyRow{tier}{dur}R1', f'ExpDlyRow{tier}{dur}R2', f'ExpDlyRow{tier}{dur}R3'],
        'on_error': [nxt]}
    return name

# 实测行内时长文本恒为 HH:MM:SS：
#   限时 idle 显示总时长（08:00:00 / 10:00:00 / 12:00:00），每日 idle 显示总时长
#   （02:00:00 / 04:00:00 / 08:00:00），已派遣/在跑的行显示倒计时（如 03:26:11）。
# 精确整点时长既能锁定目标时长档，又天然排除在跑任务。
DUR_TEXT = {
    ('ltd', 12): r'.*12:00:00.*', ('ltd', 10): r'.*10:00:00.*', ('ltd', 8): r'.*08:00:00.*',
    ('dly', 8):  r'.*08:00:00.*', ('dly', 4):  r'.*04:00:00.*', ('dly', 2):  r'.*02:00:00.*',
}
for tier, dur in LTD_CHAIN:
    for r in (1, 2, 3):
        make_row('ExpLtd', tier, dur, r, DUR_TEXT[('ltd', dur)])
for tier, dur in DLY_CHAIN:
    for r in (1, 2, 3):
        make_row('ExpDly', tier, dur, r, DUR_TEXT[('dly', dur)])

prev = 'ExpDlyGateS8'
for tier, dur in reversed(LTD_CHAIN):
    prev = make_chip(tier, dur, prev)

prev = 'ExpScrollDown'
for tier, dur in reversed(DLY_CHAIN):
    prev = make_gate(tier, dur, prev)

# ---- 引用自检：next/on_error 指向的 Exp* 节点必须存在 ----
def refs(node):
    out = []
    if isinstance(node, dict):
        for k in ('next', 'on_error'):
            v = node.get(k)
            if isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
        for e in node.get('all_of', []):
            out += refs(e)
    return out

local = set(new)
missing = sorted({r for n in new.values() for r in refs(n)
                  if r not in local and (r.startswith('Exp') or r.startswith('Expedition'))})
cross  = sorted({r for n in new.values() for r in refs(n)
                 if r not in local and not (r.startswith('Exp') or r.startswith('Expedition'))})
print(f'nodes: {len(new)}')
print('cross-file refs:', cross)
if missing:
    print('MISSING:', missing); sys.exit(1)

with open(PIPE, 'w', encoding='utf-8', newline='\n') as f:
    json.dump(new, f, indent=4, ensure_ascii=False)
    f.write('\n')
print('written:', PIPE)
print('chain tails: ExpLtdChipS12.on_error ->', new['ExpLtdChipS12']['on_error'],
      '| ExpDlyGateS8.on_error ->', new['ExpDlyGateS8']['on_error'],
      '| ExpNightGate.on_error ->', new['ExpNightGate']['on_error'])
