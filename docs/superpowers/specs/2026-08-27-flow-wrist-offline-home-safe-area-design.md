# Flow Wrist 离线主页与圆角安全区设计

日期：2026-08-27

## 背景

真实 BLE 固件启动后会停在 `FINDING THE HUB`，直到 RK3588 完成配对、订阅 Command、写入 Catalog 和首次 Snapshot。这个限制保证手环不会在状态未知时发送命令，但用户也因此无法返回主页查看界面。

开发板屏幕四角有明显圆角。现有二级页返回键靠近左上角，按钮尺寸为 50 × 42 px，实机触摸范围偏小。

## 本次目标

1. 找不到 Hub 时允许进入主页，并浏览能量和风格轮播。
2. 离线期间继续在后台搜索 Hub，不进入本地模拟模式。
3. 没有可信状态时不发送能量或风格命令。
4. 二级页返回键避开圆角，扩大实机触摸范围。

## 离线导航

连接页增加一个宽按钮，文案为 `VIEW HOME`。按钮放在屏幕下半部中央，不放在圆角附近。

点击后的行为：

- 页面切换到离线主页；
- BLE 广播、配对和状态同步照常运行；
- Hub 变为 READY 后，主页自动解除离线状态；
- 不需要用户返回连接页重新触发搜索。

离线主页使用现有暖纸白首页结构。页面显示小型 `HUB OFFLINE` 标记，不覆盖或淡化原 UI。ENERGY 和 STYLE 卡片保持可点击。

如果手环曾收到可信 Snapshot，主页显示最后一次同步的能量、风格和 BPM。如果本次启动还没有收到过 Snapshot，使用一组明确标成 `PREVIEW` 的本地展示数据：

```text
ENERGY  03 / 05
STYLE   HIPHOP
96 BPM  /  PREVIEW
```

预览状态保留原版人物插画和卡片排版。用户可以进入二级页并左右滑动查看五档能量和四种风格。点击预览项时只显示 `CONNECT HUB TO SEND`，不生成 Command，也不缓存选择。

## 状态规则

应用状态新增一个明确的“查看主页”动作。该动作只改变屏幕，不改变 BLE 链路状态。

- `CONNECTING + 非 READY`：允许进入离线主页；
- `HOME + 非 READY`：渲染可浏览的离线主页；
- `ENERGY / STYLE + 非 READY`：允许左右滑动预览和返回主页；
- `HOME + READY`：渲染正常主页；
- `SENDING` 或 `TRANSITION`：不允许通过返回动作离开；
- Hub 重连并写入 Snapshot 后，以 Hub 状态为准更新页面。

现有“非 READY 时忽略全部 UI action”的入口需要拆开处理：查看主页、打开能量/风格和返回主页可以执行。`SET_ENERGY`、`SET_STYLE`、手势预览和所有发送动作仍然被拦截。

离线轮播不允许产生待发送命令。Hub 在浏览期间连上后，以 Hub 首次 Snapshot 的真实状态重新渲染页面，不沿用离线选择。

## 圆角安全区

能量页和风格页的返回键改为 64 × 52 px，并向右下方内缩。按钮视觉位置采用 `x = 12`、`y = 8`，再叠加根容器已有的 24 px 内边距，因此实际触摸区从屏幕左上角向内约 36 px。

标题同步右移，避免和扩大后的按钮重叠。按钮外观仍使用暖纸白底、黑色描边和 `<` 图标，不改变当前插画风格。

连接页的 `VIEW HOME` 使用宽按钮，不复用左上角返回键。

## 代码范围

预计只修改以下区域：

- `components/flow_core/`：离线查看主页的状态规则；
- `components/flow_ui/flow_ui_connection.c`：`VIEW HOME` 按钮；
- `components/flow_ui/flow_ui_home.c`：无 Snapshot 时的完整预览内容；
- `components/flow_ui/flow_ui_carousel.c`：返回键安全区；
- `components/flow_ui/flow_ui.c`：非 READY 状态下的页面选择；
- `main/app_main.c`：允许离线导航动作通过；
- `tests/host/`：状态与安全区纯逻辑测试。

不修改 BLE UUID、CBOR 协议、Hub 锁定规则、手势阈值或本地模拟器。

## 验收

1. 不启动 Hub，手环停在连接页时可以点击 `VIEW HOME`。
2. 离线主页显示 `HUB OFFLINE`，首次启动显示带人物插画的本地预览数据。
3. 离线点击能量或风格可以打开轮播并左右浏览。
4. 离线点击最终预览项显示 `CONNECT HUB TO SEND`，不产生 Command。
5. Hub 在后台连接完成后，页面显示真实 Snapshot 并恢复控制。
6. 能量页和风格页的返回键在圆角屏上容易点击，返回主页只触发一次。
7. Hub 正在切歌时，返回动作仍被禁止。
8. 主机测试、模拟版构建、BLE 版构建和真机启动检查通过。
