# Flow Wrist UI Motion and Dancer Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将四个舞种人物插画嵌入手环，并把能量/风格切换改成随手指移动、140 ms 吸附的轻量 LVGL 轮播。

**Architecture:** 原始透明 PNG 只作为设计源文件，构建前由确定性脚本转成 RGB565+A8 C 数组。轮播的索引和位移计算保持纯 C，LVGL 层持有左中右三个常驻页面，拖动时只改坐标和透明度，不重建对象树。

**Tech Stack:** ESP-IDF 5.5.5、LVGL 9.5、C11、Python 3、Pillow、ESP32-S3 PSRAM

---

### Task 1: 生成并归档四个一致角色的透明插画

**Files:**
- Create: `firmware/flow-wrist/assets/source/dancer_hiphop.png`
- Create: `firmware/flow-wrist/assets/source/dancer_breaking.png`
- Create: `firmware/flow-wrist/assets/source/dancer_funk.png`
- Create: `firmware/flow-wrist/assets/source/dancer_locking.png`

- [ ] **Step 1: 生成基准角色**

调用内置图片生成器创建一张透明背景、无文字、粗黑边、低像素块面、全身居中的中性舞者，姿势为 hiphop bounce，必须清楚显示头、颈、肘、膝、手和鞋。

- [ ] **Step 2: 生成其余姿势**

以 hiphop 图片作为角色参考，分别生成 breaking footwork/freeze、funk groove、locking stop/point；只改变动作和点缀色，不改变帽子、服装和人物比例。

- [ ] **Step 3: 视觉验收并复制到工程**

逐张检查透明边缘、肢体可读性和同一角色一致性；最终源图统一保存为 1024×1024 RGBA PNG，文件名与上方列表完全一致。

- [ ] **Step 4: Commit**

```bash
git add firmware/flow-wrist/assets/source
git commit -m "assets: add Flow Wrist dancer illustrations"
```

### Task 2: 建立可复现的图片转换链路

**Files:**
- Create: `firmware/flow-wrist/tools/convert_dancer_art.py`
- Create: `firmware/flow-wrist/tests/host/test_dancer_assets.py`
- Create: `firmware/flow-wrist/components/flow_ui/assets/flow_dancer_assets.h`
- Create: `firmware/flow-wrist/components/flow_ui/assets/flow_dancer_assets.c`

- [ ] **Step 1: 写失败测试**

测试必须运行转换脚本到临时目录，并断言四个符号存在、输出尺寸均为 112×112、单图字节数不超过 64 KiB、总资源不超过 250 KiB。

- [ ] **Step 2: 验证测试失败**

Run: `python3 -m unittest firmware/flow-wrist/tests/host/test_dancer_assets.py -v`

Expected: 因转换脚本或输出符号不存在而 FAIL。

- [ ] **Step 3: 实现转换器**

脚本使用 Pillow 的 LANCZOS 缩放到 112×112，颜色量化为 RGB565，小于 8 的 alpha 设为 0，并输出 LVGL `LV_IMAGE_CF_TRUE_COLOR_ALPHA` 描述符。按名称排序输入，保证重复运行得到完全相同的 C 文件。

- [ ] **Step 4: 生成并验证资源**

```bash
python3 firmware/flow-wrist/tools/convert_dancer_art.py
python3 -m unittest firmware/flow-wrist/tests/host/test_dancer_assets.py -v
```

Expected: 4 tests PASS，总资源小于 250 KiB。

- [ ] **Step 5: Commit**

```bash
git add firmware/flow-wrist/tools firmware/flow-wrist/tests/host/test_dancer_assets.py firmware/flow-wrist/components/flow_ui/assets
git commit -m "feat: convert dancer art for LVGL"
```

### Task 3: 先用纯 C 固定轮播数学

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/include/flow_carousel_model.h`
- Create: `firmware/flow-wrist/components/flow_ui/flow_carousel_model.c`
- Create: `firmware/flow-wrist/tests/host/test_carousel_model.c`
- Modify: `firmware/flow-wrist/tests/host/run.sh`

- [ ] **Step 1: 写失败测试**

覆盖小拖动回弹、超过 52 px 切换一档、边界夹紧、快速甩动切换一档，以及输出吸附时长恒为 140 ms。

- [ ] **Step 2: 验证测试失败**

Run: `cd firmware/flow-wrist && tests/host/run.sh`

Expected: 编译失败，提示 `flow_carousel_model.h` 不存在。

- [ ] **Step 3: 实现最小模型**

公开 `flow_carousel_drag_offset()`、`flow_carousel_release()` 和 `flow_carousel_neighbor()`；位移夹在屏宽的 ±1 倍，release 结果只允许 -1、0、+1。

- [ ] **Step 4: 运行测试**

Run: `cd firmware/flow-wrist && tests/host/run.sh`

Expected: 所有 host tests PASS。

- [ ] **Step 5: Commit**

```bash
git add firmware/flow-wrist/components/flow_ui firmware/flow-wrist/tests/host
git commit -m "feat: add deterministic carousel motion model"
```

### Task 4: 用三个常驻页面实现跟手轮播

**Files:**
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_carousel.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_art.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_internal.h`
- Modify: `firmware/flow-wrist/components/flow_ui/CMakeLists.txt`

- [ ] **Step 1: 接入人物资源**

风格页按 hiphop、breaking、funk、locking 映射四张图；能量页沿用当前舞种人物，并通过速度线数量和上下 2–6 px 的阶梯动效表现 1–5 档能量。

- [ ] **Step 2: 改为实时拖动**

按下记录起点；`LV_EVENT_PRESSING` 每帧读取坐标差并同步移动左中右页面；松开后根据纯 C 模型决定切换或回弹，使用 `lv_anim_t` 在 140 ms 内吸附。

- [ ] **Step 3: 消除拖动期间重建**

拖动和吸附期间禁止 `lv_obj_clean()`；动画完成后只更新三个页面内容并恢复坐标，触控事件保持在最上层透明 hit area。

- [ ] **Step 4: 构建双配置**

```bash
cd firmware/flow-wrist
idf.py -B build-sim build
idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" build
```

Expected: 两个构建均退出 0，应用分区无溢出。

- [ ] **Step 5: 实机验收并 Commit**

烧录 simulator，连续左右拖动能量和风格各 20 次；页面必须跟手，无白屏、无误触发送、无明显撕裂。

```bash
git add firmware/flow-wrist/components/flow_ui
git commit -m "feat: add responsive illustrated wrist carousel"
```
