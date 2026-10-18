# GiantessAutoChess

《踏国》(Tread) —— 基于 **Unreal Engine 5.8** 的自走棋战斗项目。

本仓库是**公开的代码镜像 + 构建产物发布页**。开发主仓库 `splna1/Tread` 保持私有。

## 下载

可执行版本在 [**Releases**](https://github.com/splna1/GiantessAutoChess/releases) 页面：

| 版本 | 内容 | 大小 |
|---|---|---|
| [v0.1.0](https://github.com/splna1/GiantessAutoChess/releases/tag/v0.1.0) | Win64 Shipping (2026-10-18) | 1.72 GiB |

解压后直接运行 `Tread.exe`。

**系统要求**：Windows 10/11 64 位 · 8 GB 显存（RTX 3060 级别起）· DirectX 12

## 仓库内容

```
Source/          C++ 源码（模块 Tread）
Config/          引擎与项目配置（.ini）
Tools/           可重复执行的编辑器侧脚本（Python / PowerShell）
.codebuddy/      工程约定与 agent 规则
AGENTS.md        协作规则（语言、资产、动画、文档编号、验收口径）
HANDOFF_*.md     阶段交接记录
Tread.uproject   项目文件
```

**不在本仓库的两类内容**：

- **`Content/` 游戏资产** —— 按工程约定「每个 UE 资产都必须能由 `Tools/` 脚本重建」，
  资产不入库；体积（8.7 GB）也远超 GitHub 仓库上限。
- **`document/` 内部设计文档** —— 未公开。

## 从源码构建

需要 Unreal Engine **5.8** 与 Visual Studio 2022（含 C++ 游戏开发工作负载）。

```powershell
# 指向本机引擎安装位置
$env:UE_ENGINE_ROOT = "G:\epicgame\UE_5.8"

# 生成工程文件
& "$env:UE_ENGINE_ROOT\Engine\Build\BatchFiles\GenerateProjectFiles.bat" -project="Tread.uproject" -game

# 编译编辑器目标
& "$env:UE_ENGINE_ROOT\Engine\Build\BatchFiles\Build.bat" TreadEditor Win64 Development -project="Tread.uproject"

# 编译发布包
& "$env:UE_ENGINE_ROOT\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun `
  -project="$PWD\Tread.uproject" -platform=Win64 -clientconfig=Shipping `
  -cook -build -stage -pak -archive -archivedirectory="$PWD\Saved\Archives"
```

**注意**：缺少 `Content/` 时项目能编译，但关卡与资产为空。资产需要用 `Tools/` 下的脚本从源模型重建。

## 工具脚本

`Tools/` 下的脚本通过 **Unreal 的 Python 远程执行** 驱动运行中的编辑器：

```powershell
python Tools/ue_run.py <script.py>       # 在运行中的编辑器里执行脚本
python Tools/ue_mcp.py toolsets          # 查询编辑器 MCP 工具集
python Tools/ue_shot.py out.png          # 视口截图
```

前提：Project Settings → Plugins → Python → 勾选 *Enable Remote Execution*。

## 工程约定

见 `AGENTS.md`。几条关键约束：

- 资产只能由脚本生成，**绝不手改** `.uasset` / `.umap`
- 动画不手 K，关键帧来自数据源
- 验收看**截图 + JSON 报告**，不看包络
- C++ 注释用英文，文档与回复用中文

## 许可

代码部分仅供学习与参考。游戏资产、角色模型与第三方素材不在本仓库内，其授权见各自来源。
