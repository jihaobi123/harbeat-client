# HarBeat UI Style Renders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成 3 张最终 HarBeat 移动端 UI 展示图，每张并排呈现首页、音乐、设备、我的四个页面，并完整保留产品手册定义的入口、状态含义和操作关系。

**Architecture:** 先从产品手册锁定任务顺序、按钮语义、状态关系和四个底部 Tab，再为六套风格分别建立视觉锚点、版式语法和组件模型。现有四张页面图只用于核对内容，不能当作固定几何模板。最后逐张检查文字、页面完整性与流程入口，并把合格图片保存到统一目录。

**Tech Stack:** Codex 内置图像生成、产品手册 HTML、参考 PNG、人工视觉核对

---

## 评审后的范围调整

最终只深化三套：叙事插画、瑞士信息网格、新粗野插画。原 Task 4 的夜场信号、Task 6 的液态数字和 Task 7 的 Y2K 数码俱乐部停止；原 Task 2、Task 3、Task 5 分别重构为新粗野插画、叙事插画、瑞士信息网格。三套都需要先确定颜色角色和使用比例，再生成最终图。

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

- [ ] **Step 6: 区分流程与版式**

只锁定用户目标、入口名称、状态含义、动作结果和页面去向。允许重新排列区块、改变卡片结构、建立新的阅读动线，禁止把现有截图直接换色后作为新方案。

### Task 2: 生成新粗野主义套图

**Files:**
- Reference: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-fc540e77-3c50-4d5e-962a-dba2c78eb9a3.png`
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/01-neo-brutalist.png`

- [ ] **Step 1: 生成四屏展示图**

以舞台施工标识为视觉锚点。用错位模块、压边标题、工业编号、状态胶带和跨网格主按钮重新组织四页，再使用奶油纸底、粗黑描边、硬投影、酸性荧光绿、钴蓝和橙红。

- [ ] **Step 2: 检查风格与内容**

确认卡片边界清楚、关键中文可读、四屏不重叠；不能出现参考图中的设计系统说明文字。

### Task 3: 生成平面编辑插画套图

**Files:**
- Reference: `/var/folders/wr/kvlkqh0n56l8rq6t7796kkww0000gn/T/codex-clipboard-829ad3ef-fe92-41e5-8f24-b7222ef56fd8.png`
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/02-flat-editorial-illustration.png`

- [ ] **Step 1: 生成四屏展示图**

以舞者动作的连续分镜为视觉锚点。让插画承担视线引导与功能解释，分别为推荐、歌单、设备连接和个人记录建立叙事场景，再使用白底、黑色手绘线与鲜明平涂色块。

- [ ] **Step 2: 检查风格与内容**

确认版面像现代音乐杂志，四个页面仍像可操作的手机 App，不应变成纯海报。

### Task 4: 生成夜场信号套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/03-midnight-signal.png`

- [ ] **Step 1: 生成四屏展示图**

以手机到 RK3588 的信号路径为视觉锚点。沿发光信号脊柱安排连接、输出、同步和播放节点，波形与路由表达层级，矩形卡片只在必要处出现。

- [ ] **Step 2: 检查风格与内容**

确认设备状态与演出氛围突出，但音乐、个人页仍清晰；不出现低对比玻璃拟态文字。

### Task 5: 生成瑞士节拍套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/04-swiss-rhythm.png`

- [ ] **Step 1: 生成四屏展示图**

以音乐档案索引为视觉锚点。用编号、坐标、基线、字号和留白建立结构，减少传统卡片；白或浅灰底配信号红与国际蓝。

- [ ] **Step 2: 检查风格与内容**

确认高信息密度仍有稳定层级，中文不被英文标题挤压，底部导航与播放器完整。

### Task 6: 生成液态数字套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/05-liquid-digital.png`

- [ ] **Step 1: 生成四屏展示图**

以声音在空间中的流体形态为视觉锚点。主要任务依附在大块彩塑表面和层叠景深上，使用浮动 Dock、焦点球体与连续曲线建立动线；文字层保持高对比。

- [ ] **Step 2: 检查风格与内容**

确认页面年轻、轻盈，不能因为渐变和透明效果降低按钮边界与设备状态可读性。

### Task 7: 生成 Y2K 数码俱乐部套图

**Files:**
- Create: `/Users/jihaobi/Documents/New project/outputs/harbeat-ui-renders/06-y2k-digital-club.png`

- [ ] **Step 1: 生成四屏展示图**

以复古媒体操作系统为视觉锚点。使用可重排窗口、播放传输条、像素表头和金属控件重建页面层级，再加入深紫、亮粉、电青、荧光黄和少量扫描线。

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
