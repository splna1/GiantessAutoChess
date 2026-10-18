---
description: "战斗演出验收夹具的两个坑：给 AI 配板会消耗 RandomStream 从而改变 P0 的对手（配一个不行，要配全部三个 AI）；命令 RequestId 幂等，脚本里循环调命令必须每次换 id。改 Tools/battle/battle_presentation_check.py 前必读。"
---

# 验收夹具：配板会换对手、RequestId 会吞命令

`Tools/battle/battle_presentation_check.py` 给玩家/AI 摆"商店发不出来的棋盘"（演示、验收用）。两个坑都
在 2026-10-17 那轮踩实：

## 1. 配板消耗 `RandomStream` → P0 的对手换人

`GrantUnitToPlayer` 里每个单位都要跑一次 tier 洗牌（`TreadM2PactRuntime.cpp:1059`
`RandomStream.RandRange`），它和 `BuildPairings` 用的是**同一条随机流**。所以"只给 P1 配混编棋盘"这
个想法会改变洗牌结果：实测 P0 的对手从 P1 漂到了 P3，证据镜头里出现的仍是 P3 的灰盒 3 人（全近战），
方案 C 想要的"敌方混编接敌"根本没进画面。换句话说，**给谁配板就等于改谁跟 P0 打**。

**How to apply:** 要"敌方也有戏"，就给 **P1/P2/P3 三个 AI 都配**同一套混编棋盘（`MIXED_WANT`），
`board_ids(exclude=...)` 累加前面已选角色避免抽干卡池；**不要**试图"先复算洗牌、再单独配那个人"——洗牌在
deploy 时才跑，复算很脆。真正被配对的是谁，由 `deploy_and_start_battle` 之后读
`match_state.last_battle_result.pairings` 记进状态（`opponent`），别靠猜。

## 2. `RequestId` 幂等会吞掉循环里的命令

控制器对同 `RequestId` 的第二次调用直接返回 `TryGetProcessedRequest` 的缓存结果（不执行）。验收脚本
里"同一 tag 连续移动 6 个单位"如果共用 `tag + "-p1"`，第 2–6 次全部被吞，棋盘上只有一个单位落到目标格，
而报告还显示 `accepted`。

**How to apply:** 每次命令都要独立 id（`"%s-%s-%d" % (tag, pid.lower(), slot)`）。同理，
`start` / `deploy` / `guards` 各自用不同后缀，重跑同一 tag 时也要意识到上一轮 id 已被处理过。

Related: [[tread-tarray-removeat-aliasing]], [[tread-crash-dump-tools]], [[tread-ue5-verify]]
