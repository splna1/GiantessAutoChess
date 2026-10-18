---
name: tread-ue5-toolchain
description: "在 Tread / 《踏国》UE5 工程（E:\\AI\\Tread\\Tread，UE 5.8.3）里干活时使用：驱动 Unreal Editor、批量执行编辑器侧 Python、导入导出资产、跑 PIE、改 C++ 或 UE 资产、排查编辑器崩溃与日志。触发词：Tread、UE 编辑器、Unreal、PIE、uasset、umap、Tools 脚本、ue_run、ue_mcp。"
---

# Tread / UE5 工程工作约定

## 环境

| 项 | 值 |
|---|---|
| 工程 | `E:\AI\Tread\Tread`（模块 `Tread`） |
| 引擎 | `G:\epicgame\UE_5.8` —— **不在 C 盘**，注册表也查不到，必须显式给 `$env:UE_ENGINE_ROOT="G:\epicgame\UE_5.8"` |
| Blender | `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe` |
| 控制台 | **GBK**，脚本输出只用 ASCII（别用 `✓`，会 `UnicodeEncodeError` 崩掉，用 `[OK]` / `ERROR:`） |

**本工程不是 git 仓库。改源码前先手备份。**

## 用哪个接口

1. **直接操作编辑器**（摆 Actor、读属性、改资产、Live Coding 重编 C++）→ UE5 MCP。它是引擎自带的 `ModelContextProtocol` + `AllToolsets` 插件（`Tread.uproject` 里已启用），协议见 `unreal-mcp-routing` skill。**需要 UnrealEditor 在运行**。
2. **日常大部分活** → 跑 `Tools/` 下的脚本，不用 skill。

## 命令行接口（真正常用的）

```bash
python Tools/ue_run.py <script.py> [args]   # 把编辑器侧脚本送进运行中的编辑器（Python 远程执行）—— 最常用
python Tools/ue_run.py -c "<python>"        # 一行式查询

python Tools/ue_mcp.py toolsets                     # 看 MCP 有哪些工具集
python Tools/ue_mcp.py describe <toolset>
python Tools/ue_mcp.py call <toolset|-> <tool> '<json>'
python Tools/ue_mcp.py pyfile <editor_script.py>    # 走 MCP 的 Python 执行通道跑脚本

python Tools/ue_shot.py <out.png> [x y z pitch yaw roll] [--annotate] [--warm N]
sh Tools/ue_logcheck.sh <start_line>        # 从日志第 N 行起 grep 材质/shader/python 问题
sh Tools/ue_restart.sh [max_wait_s]         # 编辑器崩了拉起，并等到远程执行可用
```

`ue_run.py` 的前提是一次性设置（见 `Tools/paris/00_enable_remote_exec.md`）：Project Settings → Plugins → Python → Enable Remote Execution，组播 `127.0.0.1` / `239.0.0.1:6766`。

## 铁律

- **所有可重复脚本放 `Tools/`。每个 UE 资产都必须能由脚本重建。**
- **`.uasset` / `.umap` 禁止手改** —— 只能由脚本、MCP 或编辑器操作产生。
- **工程实际状态优先于文档**；发现冲突必须写进 `document/100_DOCUMENT_INDEX.md` §1。
- **运行结果一律以 `Saved/Reports/*.json` 为准**，不看文档里的转述。
- 回复与文档用**中文**；代码注释用**英文**。
- **不要主动 taskkill 主人在用的编辑器。** 崩了可以 `ue_restart.sh` 拉起（本轮拉过两次），但不许杀。

## 不可重议的决策

这些都已经有实测结论，**不要再回头试**（原始记录：根目录 `HANDOFF_N2.md` §4）：

1. 判"游戏里到底画出了什么"**只用 `HighResShot` + 差分**。细节见 `tread-ue5-verify` skill。
2. **MMD 模型按厘米制导出**。`FBX_SCALE_ALL` 无效 —— 实测 UE 仍把根骨缩成 100。
3. 跨骨架重定向**必须对齐 target retarget pose**，并且要按**关节角度**验收（只看缩放和包围范围会漏掉手臂反向 100°）。
4. **IK Rig / IK Retargeter 一律"取回 + 原地重配"，绝不删除重建。** 删掉被引用的 IK Rig 会让编辑器 `EXCEPTION_ACCESS_VIOLATION` 崩掉且不留转储。
5. **动画不许手 K。** 关键帧只来自 GP PSA 数据；跨骨架只能重定向。
6. **presenter 的 C++ 不用改**（N2 三个缺陷全在资产侧）。组件创建顺序不是问题，曾被误判。
7. **地图切换（`load_map`）必须单独一次调用**，同一帧持有世界引用再切图会 fatal 崩溃。
8. **`slomo` 是控制台变量，跨 PIE 会话存活。** 拍照用的 `slomo 0` 收尾必须复位，否则下一次 PIE 里 presenter 永远不 tick。

## 环境雷

（原始记录：`HANDOFF_N2.md` 附录 C）

- Python 远程执行里**不能 `time.sleep`**（会卡游戏线程）——等待一律放主机侧轮询。
- `unreal.Rotator` 位置参数顺序是 `(roll, pitch, yaw)`，**永远按名字传**。
- 长任务日志会缓冲：实时进度看 `Saved/Logs/ue_run_last.log`，不要等 stdout；`ue_run.py` **退出码不可靠**，看输出里的 `status=OK` / `status=FAIL`。
- Git Bash 会把 `/Game/...` 改写成 `C:/Program Files/Git/Game/...`，需要 `MSYS_NO_PATHCONV=1`。
- 编辑器重启后回到默认图 `M0_Paris_Board`，要手动切回 `M3_Paris_Match`。
- `Content/Tread/Characters/MMD/` 下有 **1126 个 `.uasset`**，对该目录递归 `list_assets` 偏重，曾导致连接被重置。

## 文档台账

- 进程记录一律进 `document/`，按编号命名。**新建前先 glob `document/14*.md` 占号**（其他会话也在占号）。
- 编号 100 以下已归档（见 `document/146_UE5_文档整理_编号100以下归档_2026-10-09.md`）。
- 索引与权威来源表：`document/100_DOCUMENT_INDEX.md`。
- 管线与脚本总览：`document/10_UE5_TECH_PIPELINE.md`。
- 不加编号的交接文档放工程根目录（如 `HANDOFF_N2.md`），不进 `document/`。
