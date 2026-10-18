---
name: unreal-python-struct-aliasing
description: UE Python 里 unreal.Transform / Vector 这类结构体包装是"同一份数据"的引用，赋值不等于拷贝——改了副本会连源一起改，曾把破坏试验的碎片全缩到 1% 而"测出"了一个假的帧率。
---

# UE Python：结构体赋值是别名，不是拷贝

## 症状

写 `hidden = transform` 之后再 `hidden.scale3d = transform.scale3d * 0.01`，**源 `transform` 也一起变成 0.01**。
用它去放碎片/替身时，所有替身都以 1% 大小落在场景里，肉眼几乎看不见，帧率却很"正常"——**测量结果完全失真**（2026-10-18 的建筑破坏试验就是这么把"废墟 57.1 fps / 碎片 45.7 fps"测出来的，后已撤回）。

## 原因

`unreal.Transform`、`unreal.Vector`、`unreal.Rotator` 等在 Python 侧是 **UStruct 的包装对象**；从属性/getter 拿到的对象与源共享底层数据，简单赋值不会复制。

## 做法

- 要改副本：`copy = source.copy()`（`Transform` / `Vector` 都有 `copy()`）。
- 想彻底避免：直接构造新值，例如 `unreal.Transform(Location, Rotation, Scale)`。
- 依赖"我改了副本、源不变"的代码都要复查。

## 相关 API 差异（同一轮踩到的）

- `Transform` 的缩放字段叫 **`scale3d`**，不是 `scale`；旋转字段是 **`Quat`**。
- `unreal.Transform(Translation, Rotation, Scale3d)` 的第二个参数要 **`Rotator`**，传 `Quat` 会报 `Cannot nativize 'Quat' as 'Rotator'`。
- 想按偏移放置：`WorldTransform = BuildingTransform.multiply(OffsetTransform)`（局部偏移先构造 `Transform`，再乘）。
- ISM 没有逐实例可见性开关，隐藏实例的廉价办法是缩放；**因此别名 bug 会直接让"隐藏"和"替身"一起缩小**，格外容易骗过眼睛。

## 验证

改完先量一个实例的世界变换（`get_instance_transform`）并截图；数字正确 + 画面正确才算过。只看帧率不算数。
