---
description: "UE 5.8 TArray::RemoveAt 会让调用方按 const FString& 传进来的数组成员悬垂（use-after-free），2026-10-17 崩过一次；命令函数里先拷副本再用。改 TreadM1MatchController 的命令/夹具代码前必读。"
---

# `RemoveAt` + `const FString&` 入参 = use-after-free

`ATreadM1MatchController::MoveUnitToBoard(PlayerId, const FString& UnitInstanceId, ...)` 这类命令函数，
如果调用方把**数组元素里的字符串**按 const 引用传进来，函数内部又 `RemoveAt` 掉那个元素，那么之后
再用这个引用就是读已释放内存。UE 5.8 的 `TArray::RemoveAt` 默认允许缩容（shrink），元素缓冲区被还回
堆，分配器把 freelist 链接写进释放块首部，`FString` 的 `Data` 指针被覆盖成 0 而 `Num` 还在。

**2026-10-17 实崩（已结案）**：`StockBoardForFixture`（`TreadM2PactRuntime.cpp:1769`）传
`Player->BenchUnits.Last().UnitInstanceId`；`MoveUnitToBoard` 里 `BenchUnits.RemoveAt(Index)` 之后做
`BenchUnitInstanceIds.Find(UnitInstanceId)` → `FString::Equals` 两边 `Num>1` → `Strcmp(有效串, nullptr)`
→ 读 0x0（`TArray<FString>::Find()` `Array.h:1559`）。寄存器互证：`rdx=0`（入参字符指针）、
`rax=0x50='P'`（元素串首字符）。P1 每次都恰好 1→0，所以必崩；P0 台位容量大、`RemoveAt` 不触发缩容，
多年没崩纯属侥幸。

**How to apply:**
- 命令函数里凡是"先 `RemoveAt` 再引用 `UnitInstanceId`"的地方，一律先 `FTreadM1UnitInstance Copy = Arr[Index];`
  再 `RemoveAt`，后续只用 `Copy.UnitInstanceId`。已修：`MoveUnitToBoard`（`TreadM1MatchController.cpp:2137/2145`）、
  `MoveUnitToBench`（2186/2197）。
- 已审计**不需要**改的两处：`SellUnit`（先拷 `SoldUnit` 再 `RemoveAt`，参数只在删之前比较）、
  `DestroyTransformClone`（用 `DestroyedClone` 副本）。
- 复查手法：搜 `RemoveAt(` 的每一处，看该函数同一作用域里还有没有 `UnitInstanceId` / `FString&` 参数在用。
- 新增同类命令时，最省事的写法是函数**第一行拷贝**：`const FString UnitId = UnitInstanceId;`。

Related: [[tread-battle-fixture-pitfalls]], [[tread-crash-dump-tools]], [[tread-m2-runtime-notes]]
