# HarBeat UI Style Renders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成 6 张 HarBeat 移动端 UI 展示图，每张并排呈现首页、音乐、设备、我的四个页面，并完整保留产品手册定义的入口、状态含义和操作关系。

**Architecture:** 先从产品手册和现有四张页面图中锁定内容骨架，再对六套风格分别生成。每次生成只改变视觉语言，不改变页面顺序、信息层级、导航、按钮语义或设备流程。最后逐张检查文字、页面完整性与流程入口，并把合格图片保存到统一目录。

**Tech Stack:** Codex 内置图像生成、产品手册 HTML、参考 PNG、人工视觉核对

---

### Task 1: 锁定四屏内容与流程

**Files:**
- Read: `/Users/jihaobi/Downloads/harbeat-mobile-product-handbook.html`
- Read: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-9fdcee38-313f-4c6f-b7a6-6cc50dfe36e0.png`
- Read: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-2d41896e-2e70-4257-8317-508871511a15.png`
- Read: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-d99c5318-c4bb-4b14-81ad-12cf94fea319.png`
- Read: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-7346cbbc-6205-46df-99c3-94983d01e3eb.png`

- [ ] **Step 1: 核对固定导航**

确认四个底部 Tab 的顺序始终为首页、音乐、设备、我的，迷你播放器始终在底部导航上方。

- [ ] **Step 2: 核对首页流程入口**

首页保留 RK3588 在线状态、今晚的 Cypher、继续准备、手机播放和连接设备。设备卡通往设备流程，Cypher 卡通往准备流程。

- [ ] **Step 3: 核对音乐流程入口**

音乐页保留推荐、搜索、曲库、歌单四个分区，以及本周练习、Battle Warm-up、编辑、删除、新建歌单。界面要看得出后续可进入歌曲详情、试听、保存和合法资源导入。

- [ ] **Step 4: 核对设备流程入口**

设备页保留 RK3588 在线状态、Main Out / Stereo、延迟与曲目事实、Pad 预设、播放测试音和配对入口。页面要看得出设备列表、四位配对码、设备面板、Pad 编辑、确认覆盖并同步的顺序。

- [ ] **Step 5: 核对个人页边界**

个人页保留 FENG / DANCER、舞种与等级、画像控制说明、Cypher Session 使用记录，并明确活动现场操作不改变长期推荐画像。

### Task 2: 生成新粗野主义套图

**Files:**
- Reference: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-fc540e77-3c50-4d5e-962a-dba2c78eb9a3.png`
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/01-neo-brutalist.png`

- [ ] **Step 1: 生成四屏展示图**

使用奶油纸底、粗黑描边、硬投影、酸性荧光绿、钴蓝和橙红。四台手机完整并列，沿用 Task 1 的全部内容。

- [ ] **Step 2: 检查风格与内容**

确认卡片边界清楚、关键中文可读、四屏不重叠；不能出现参考图中的设计系统说明文字。

### Task 3: 生成平面编辑插画套图

**Files:**
- Reference: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-829ad3ef-fe92-41e5-8f24-b7222ef56fd8.png`
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/02-flat-editorial-illustration.png`

- [ ] **Step 1: 生成四屏展示图**

使用白底、黑色手绘线、黄色、天蓝、粉色和橙色平涂色块。插画可以表现舞者、音箱、唱片与节奏动作，但不能遮挡按钮、状态或数据。

- [ ] **Step 2: 检查风格与内容**

确认版面像现代音乐杂志，四个页面仍像可操作的手机 App，不应变成纯海报。

### Task 4: 生成夜场信号套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/03-midnight-signal.png`

- [ ] **Step 1: 生成四屏展示图**

使用深黑、紫外光、电光青、荧光绿、波形和信号线。透明层只用于装饰与次级状态，正文和按钮使用实色高对比。

- [ ] **Step 2: 检查风格与内容**

确认设备状态与演出氛围突出，但音乐、个人页仍清晰；不出现低对比玻璃拟态文字。

### Task 5: 生成瑞士节拍套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/04-swiss-rhythm.png`

- [ ] **Step 1: 生成四屏展示图**

使用白色或浅灰底、严格网格、巨大无衬线标题、信号红和国际蓝。信息用编号、细线和对齐关系组织。

- [ ] **Step 2: 检查风格与内容**

确认高信息密度仍有稳定层级，中文不被英文标题挤压，底部导航与播放器完整。

### Task 6: 生成液态数字套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/05-liquid-digital.png`

- [ ] **Step 1: 生成四屏展示图**

使用浅色珠光渐变、半透明彩塑卡片、圆润几何和少量铬感高光。文字承载层使用高遮罩或实色底。

- [ ] **Step 2: 检查风格与内容**

确认页面年轻、轻盈，不能因为渐变和透明效果降低按钮边界与设备状态可读性。

### Task 7: 生成 Y2K 数码俱乐部套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/06-y2k-digital-club.png`

- [ ] **Step 1: 生成四屏展示图**

使用深紫底、亮粉、电青、荧光黄、叠影标题、扫描线、复古播放器符号和小面积金属质感。

- [ ] **Step 2: 检查风格与内容**

确认潮流装饰集中在标题和边缘，功能按钮仍有稳定边界，不能把界面做成不可操作的演出海报。

### Task 8: 汇总验收与交付

**Files:**
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/01-neo-brutalist.png`
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/02-flat-editorial-illustration.png`
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/03-midnight-signal.png`
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/04-swiss-rhythm.png`
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/05-liquid-digital.png`
- Verify: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/06-y2k-digital-club.png`

- [ ] **Step 1: 逐张核对页面完整性**

每张图必须有四台完整手机，页面顺序为首页、音乐、设备、我的，底部导航和迷你播放器不缺失。

- [ ] **Step 2: 逐张核对流程入口**

核对首页、音乐、设备和个人页的操作入口与状态文案；任何为了风格被删除、改名或移位到不可识别位置的入口都需要重新生成。

- [ ] **Step 3: 横向核对风格差异**

六张图保持同一内容密度和构图，视觉语言彼此独立。新粗野主义和平面插画分别参考用户图片，其余四套使用各自定义的色彩、字体与材质规则。

- [ ] **Step 4: 展示最终图片**

在最终回复中逐张展示六张图片，并提供工作区中的可点击文件链接。
