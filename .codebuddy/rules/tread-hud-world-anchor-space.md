---
description: "把 ProjectWorldToScreen 的视口像素当成本地坐标画进 Slate，会把 HUD 上所有世界锚定元素缩到左上角（2026-10-17 头顶血条就是这样）；世界锚定一律先换算到设计空间。改 TreadM1MatchWidget 里任何随单位走的 HUD 前必读。"
---

# 世界锚定的 HUD 元素：先换算坐标空间

HUD 是 Slate 直绘。`TreadUI::Quad/Text` 收到的是**控件本地像素**，而工程的排版写法是
`Ref(x) = x * LayoutScale`、`RefVec(x, y)`（`LayoutScale = min(LocalSize/1920, LocalSize/1080)`），
所以"设计像素 → 本地像素"这一步已经由 `Ref/RefVec` 负责。

`UGameplayStatics::ProjectWorldToScreen` 返回的却是**视口像素**（PIE 下常见 1074×598 这种物理尺寸），
两者之间差一个 **DPI/布局缩放**（本机约 0.554）。直接把投影结果当本地坐标画：

```cpp
const FVector2D Local = Screen / LayoutScale;              // 错：Screen 不是本地像素
DrawBlock(..., RefVec(Local.X - 46, Local.Y - 30), ...);   // 画出来 ≈ Screen × 0.55，挤向左上
```

效果就是 2026-10-17 主人看到的现象：**头顶血条、阶层/星级标签全堆在画面左上角**，而且彼此重叠。

**How to apply:** 新加任何"跟着单位/格子走的 HUD 元素"时，用

```cpp
FVector2D UTreadM1MatchWidget::ScreenToDesign(const FGeometry& Geometry, const FVector2D& Screen) const
{
    const float PaintScale = FMath::Max(Geometry.GetAccumulatedLayoutTransform().GetScale(), KINDA_SMALL_NUMBER);
    return Screen / (PaintScale * FMath::Max(LayoutScale, KINDA_SMALL_NUMBER));
}
```

（等价范式在别处已有：前台用 `Geometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition())`，
拖拽用 `Geometry.LocalToAbsolute(RefPosition * ReferenceScale())`。）

**自查办法：** 编辑器里量两个数——`PlayerController.GetViewportSize()`（视口像素）和控件 `GetLocalSize()`
（设计像素，通常 1080p 设计空间）；两者不等就说明必须换算。别靠"看起来差不多"。

Related: [[tread-slate-maketext-letterspacing]], [[tread-shot-showui-crash]], [[tread-ui-style-prototype]]
