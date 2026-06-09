# HarBeat DJ 频段转场引擎方案评估文档

版本：v1.0
日期：2026-06-07
适用对象：项目负责人、产品、后端、移动端、RK3588 播放端开发人员
对应功能：新增基于高中低频的 DJ EQ 频段混音转场能力
核心结论：第一版只需要 MP3，不需要 stems 文件。

---

## 1. 一句话结论

HarBeat 可以新增一个独立的 **DJ 频段转场引擎**，让系统在切歌时不再只是普通 crossfade，而是像 DJ 一样控制两首歌的 Low / Mid / High、fader、filter 和少量 FX。

第一版的正确边界是：

```text
音源：只需要 MP3
分析：Jetson 离线分析 MP3，生成 mix_profile
执行：RK3588 实时解码 MP3，在 PCM 上做 EQ / fader / filter
不做：stems 分轨、人声/鼓/贝斯单独文件、预渲染混音片段
```

这个功能应当作为现有 DJ Control 的转场增强，而不是重做选歌、同步、播放系统。

---

## 2. 为什么值得做

HarBeat 当前已经有舞种切歌、能量切歌、候选池预取、RK 播放执行等基础能力。新增 DJ 频段转场后，可以明显提升“听起来像 DJ”的程度。

原本普通 crossfade 的问题：

```text
A 歌音量逐渐降低
B 歌音量逐渐升高
```

听感问题：

```text
两首歌鼓和贝斯可能叠在一起，低频变糊
两首歌人声可能同时出现，歌词混乱
目标歌突然进入，舞者来不及适应节奏
能量切换不够像现场 DJ 控场
```

新增频段转场后：

```text
新歌可以先进入高频节奏
中频旋律/人声延后进入
低频在小节第一拍完成换底
必要时加入 filter / echo / loop
```

用户听到的是：

```text
新歌不是硬闯进来，而是一层一层接管现场。
```

---

## 3. 外部依据

### 3.1 DJ 软件/设备确实以 EQ、fader、filter 为核心

Serato Play 官方说明中明确包含 EQ、crossfader、filter 等控制项，这说明基础 DJ 混音并不是只有音量推子，而是频段和音量共同控制。
来源：https://support.serato.com/hc/en-us/articles/360001274856-Serato-Play

Pioneer DJM-900NXS 产品说明中写到每个通道都有 3-band EQ isolator，可独立控制 high、mid、low 频率。
来源：https://www.pioneerdj.com/en/product/dj-mixers/djm-900nxs/

Native Instruments Traktor 的 EQ/Filter 文档中提到 Z ISO 是 full-kill isolator，说明 DJ 软件里“彻底切掉某个频段”的思路是成熟功能。
来源：https://support.native-instruments.com/hc/en-us/articles/210273465-EQ-and-Filter-Models-in-TRAKTOR-PRO-2

### 3.2 DJ 教程支持“低频换底”和“分层交接”

DJ.Studio 的 EQ mixing 教程把 EQ 混音解释为通过 high / mid / low 频段交换来避免两首歌元素打架，并提到常见做法是先处理高频，再处理中频，最后处理低频。
来源：https://dj.studio/blog/dj-eqmixing

Digital DJ Tips 的教程把 bassline swap 作为基础 DJ 转场技巧之一：进来的歌先关掉 low EQ，之后在合适位置交换两首歌的 bass。
来源：https://www.digitaldjtips.com/rock-the-dancefloor/five-basic-dj-transitions/

Club Ready DJ School 对 bass swap 的提醒也很重要：硬切低频不能乱用，如果时机不对，转场会突然变空。因此我们需要区分“软低频换底”和“硬低频换底”。
来源：https://www.clubreadydjschool.com/tribe-talk/getting-started/bass-swapping-dont-make-this-common-mistake/

### 3.3 自动 DJ 研究支持 EQ + fader 路线

Automatic DJ Transitions with Differentiable Audio Effects and GANs 这篇论文中，生成器使用 equalizer 和 fader 两个可微 DSP 组件去学习真实 DJ 转场。这说明“用 EQ 曲线 + fader 曲线生成自动转场”是自动 DJ 领域合理路线。
来源：https://arxiv.org/abs/2110.06525

Automatic Detection of Cue Points for DJ Mixing 把 cue point / switch point 作为自动构造 DJ 转场的关键，并基于专业 DJ 规则进行检测。
来源：https://arxiv.org/abs/2007.08411

---

## 4. 和 HarBeat 当前架构的匹配度

根据现有项目交接文档，HarBeat 是三端协作：

```text
手机 App
  - 用户登录、DJ Control UI、选择舞种/能量、确认切歌

Jetson / 后端
  - FastAPI API、曲库、音频分析、舞种/能量策略、DJ 计划生成

RK3588 / 现场播放盒子
  - edge-agent 接收 App 控制
  - audio-engine 执行播放、xfade、FX
  - sync-worker 从 Jetson 拉取并缓存音频
```

新增 DJ 频段转场正好匹配这个架构：

```text
Jetson：生成 eq_band_mix 转场计划
App：展示推荐混音方式，用户确认
RK3588：实时执行 EQ / fader / filter / FX
```

不需要改变的部分：

```text
不改变登录
不改变曲库同步
不改变候选池准备
不改变 RK sync-worker 缓存流程
不改变现有能量/风格切歌选歌逻辑
```

只需要增强：

```text
transition_strategy.py
mixer_rules.py
/api/dj/transitions/plan
RK audio-engine 的 xfade 执行能力
Flutter DJ Control 的混音方式选择 UI
```

---

## 5. MP3 是否够用

结论：**够用。**

第一版做的是 EQ 频段混音，不是 stem 分轨混音。

### 5.1 EQ 频段混音

EQ 频段混音处理的是整首歌的频率范围：

```text
Low：低频，鼓、贝斯、身体重心
Mid：中频，人声、旋律、乐器主体
High：高频，hi-hat、镲片、空气感
```

它的输入只需要：

```text
A.mp3
B.mp3
```

系统内部流程：

```text
MP3 → 解码成 PCM → 实时做 EQ / fader / filter → 输出到音箱
```

### 5.2 Stem 分轨混音

Stem 混音处理的是单独声部：

```text
vocal.wav
-drums.wav
bass.wav
instrumental.wav
```

只有当我们想实现下面这些能力时，才需要 stems：

```text
单独关闭人声
单独保留鼓
单独保留贝斯
A 歌人声 + B 歌鼓组合
Drums / Vocal / Instrument 独立控制
```

第一版不做这些。

### 5.3 第一版边界

| 功能 | 是否需要 stems | MP3 是否足够 |
|---|---:|---:|
| 丝滑融合 | 否 | 是 |
| 软低频换底 | 否 | 是 |
| 硬低频换底 | 否 | 是 |
| 鼓点先入 | 否 | 基本是 |
| 人声保护 | 否，但只是避让 | 基本是 |
| 扫频过渡 | 否 | 是 |
| 炸场强切 | 否 | 是 |
| 单独关闭人声 | 是 | 否 |
| 单独控制鼓/贝斯/伴奏 | 是 | 否 |

---

## 6. 用户能听懂的策略库

App 不应该展示 Low / Mid / High 旋钮，而应该展示用户能理解的效果。

### 6.1 自动推荐

系统根据舞种、两首歌的低频冲突、人声冲突、鼓点开头、能量变化，自动选一种方式。

适合默认使用。

### 6.2 丝滑融合

适合：

```text
House
Locking
Waacking
All Style
普通练习
```

听感：

```text
新歌慢慢浮出来，旧歌自然退掉。
```

内部动作：

```text
B 歌高频先进
B 歌中频慢慢进
最后低频软交换
```

### 6.3 软低频换底

适合：

```text
House
Locking
Waacking
All Style
不需要强冲击的稳定切歌
```

听感：

```text
脚下重心慢慢从 A 歌换到 B 歌，不突兀。
```

内部动作：

```text
B Low 前期压低
A Low 保留
到段落边界附近，A Low 下，B Low 上
```

### 6.4 硬低频换底

适合：

```text
Hip-hop
Breaking
Popping
Krump
Battle warm-up
```

听感：

```text
到某个第一拍，地板明显换了。
```

内部动作：

```text
B Low 前面几乎关闭
B High / 鼓点先进入
到小节第一拍，A Low 快速关，B Low 快速开
```

### 6.5 鼓点先入

适合：

```text
Hip-hop
Breaking
Popping
Locking
Cypher
```

听感：

```text
新歌先给舞者一个新的拍子，不急着给人声和旋律。
```

内部动作：

```text
B High percussion 先进
B Mid 少量进入
B Low 暂时关闭
```

### 6.6 人声保护

适合：

```text
K-pop
Jazz Funk
Waacking
Vocal Hip-hop
编舞展示
```

听感：

```text
不会两个人一起唱，歌词和动作点不乱。
```

内部动作：

```text
如果 A 正在唱，B Mid 暂时压低
B 只露一点高频节奏
等 A vocal 降低后再打开 B Mid
```

注意：第一版是“人声避让”，不是“人声分离”。

### 6.7 扫频过渡

适合：

```text
House
Waacking
Popping
两首歌元素太满时
```

听感：

```text
新歌像从远处慢慢打开，旧歌慢慢变薄。
```

内部动作：

```text
B 歌先通过 filter 进入
A 歌反向 filter 退出
最后完成低频交接
```

### 6.8 炸场强切

适合：

```text
Krump
Battle
用户主动选择炸场
能量大幅上升
```

听感：

```text
旧歌被甩出去，新歌直接砸下来。
```

内部动作：

```text
A 最后 1-2 拍 echo / filter / kill
B 在下一拍或 drop 点全频进入
```

限制：不建议第一版自动默认使用，应作为用户主动效果。

---

## 7. 自动推荐规则

第一版不用复杂模型，规则足够。

```text
如果两首歌低频都强：
  推荐低频换底
  如果舞种是 Hip-hop / Breaking / Krump：硬低频换底
  否则：软低频换底

如果当前歌和目标歌人声都强：
  推荐人声保护

如果目标歌有干净鼓点 intro：
  推荐鼓点先入

如果两首歌编曲都很满：
  推荐扫频过渡或缩短重叠时间

如果用户选择炸场，或能量提升很大：
  推荐炸场强切

否则：
  推荐丝滑融合
```

优先级建议：

```text
用户主动选择 > 安全风险判断 > 舞种倾向 > 默认丝滑融合
```

---

## 8. 需要新增的音乐分析数据

每首 MP3 需要生成一个 `mix_profile_v1`，作为转场引擎依据。

第一版只需要 5 类数据：

| 数据 | 作用 |
|---|---|
| BPM / beat grid | 保证切歌不乱拍 |
| phrase grid | 低频换底卡在段落点 |
| low/mid/high 曲线 | 判断频段怎么交接 |
| vocal_density | 判断是否需要人声保护 |
| drum_density / clean_intro | 判断能否鼓点先入 |

建议结构：

```json
{
  "mix_profile_v1": {
    "bpm": 96.0,
    "beat_grid": [],
    "downbeat_grid": [],
    "phrase_grid": [],
    "band_energy": {
      "low_curve": [],
      "mid_curve": [],
      "high_curve": []
    },
    "density": {
      "vocal_density_curve": [],
      "drum_density_curve": [],
      "bass_density_curve": [],
      "high_hat_density_curve": []
    },
    "mix_flags": {
      "has_clean_intro": true,
      "has_drum_intro": true,
      "has_vocal_intro": false,
      "has_strong_bass_intro": false,
      "has_usable_outro": true
    },
    "safe_points": {
      "mix_in_points": [],
      "mix_out_points": [],
      "bass_swap_points": [],
      "hard_cut_points": []
    }
  }
}
```

---

## 9. 风险评估

### 9.1 技术风险

| 风险 | 等级 | 说明 | 控制方式 |
|---|---:|---|---|
| beat grid 不准 | 中 | 会导致低频换底不在拍上 | 第一版允许 fallback 到普通 xfade |
| 人声检测不准 | 中 | 可能人声保护误判 | 文案定义为“人声避让”，不是分离 |
| RK 实时 EQ 爆音 | 高 | 两首歌叠加可能 clipping | 固定 headroom -6 dB + limiter |
| EQ 参数突变有杂音 | 中 | 可能出现 click/pop | 参数平滑 20-50 ms |
| 策略过多导致不稳定 | 中 | 第一版不要做太多效果 | 只做 5 个核心策略 |

### 9.2 产品风险

| 风险 | 等级 | 说明 | 控制方式 |
|---|---:|---|---|
| 用户看不懂参数 | 高 | Low/Mid/High 不适合普通用户 | UI 只展示“丝滑/强节奏/人声保护”等 |
| 炸场效果滥用 | 中 | 影响练习稳定性 | 不默认自动使用，需用户主动选择 |
| 和能量/风格切歌混淆 | 中 | 用户不知道哪个按钮负责什么 | 选歌和混音分离，文案说明清楚 |

---

## 10. 分阶段建议

### 第一阶段：MVP，可上线验证

范围：

```text
eq_band_mix 模式
丝滑融合
软低频换底
硬低频换底
人声保护
扫频过渡
```

不做：

```text
stems
自动 scratch
复杂 echo/reverb
复杂 loop bridge
```

验收标准：

```text
App 能选择混音方式
Jetson 能返回 transition_plan
RK 能执行 EQ + fader 转场
转场不爆音、不静音
失败时回退普通 xfade
```

### 第二阶段：增强 DJ 感

增加：

```text
鼓点先入
循环桥接
炸场强切
更细的舞种映射
更好的 safe point 检测
```

### 第三阶段：Stem / Part ISO

增加：

```text
vocal / drums / bass / instrumental stems
或者接入实时分离模型
```

但这不是第一版必须项。

---

## 11. 项目组决策建议

建议立项，第一版按以下边界执行：

```text
功能名：DJ 频段转场引擎
内部模式：eq_band_mix
音源要求：只需要 MP3
分析产物：mix_profile_v1
执行位置：RK3588 audio-engine
用户入口：DJ Control 页面混音方式选择
首批策略：丝滑融合、软低频换底、硬低频换底、人声保护、扫频过渡
核心安全：headroom、limiter、参数平滑、fallback 到普通 xfade
```

不建议第一版做 stems，因为它会显著增加分析耗时、存储、播放复杂度和稳定性风险。

---

## 12. 参考资料

1. Serato Play - EQ / Crossfader / Filter controls
   https://support.serato.com/hc/en-us/articles/360001274856-Serato-Play

2. Pioneer DJM-900NXS - 3-band EQ isolator
   https://www.pioneerdj.com/en/product/dj-mixers/djm-900nxs/

3. Native Instruments Traktor EQ and Filter Models
   https://support.native-instruments.com/hc/en-us/articles/210273465-EQ-and-Filter-Models-in-TRAKTOR-PRO-2

4. DJ.Studio - DJ EQ Mixing
   https://dj.studio/blog/dj-eqmixing

5. Digital DJ Tips - Five Basic DJ Transitions
   https://www.digitaldjtips.com/rock-the-dancefloor/five-basic-dj-transitions/

6. Club Ready DJ School - Bass Swapping Common Mistake
   https://www.clubreadydjschool.com/tribe-talk/getting-started/bass-swapping-dont-make-this-common-mistake/

7. Automatic DJ Transitions with Differentiable Audio Effects and GANs
   https://arxiv.org/abs/2110.06525

8. Automatic Detection of Cue Points for DJ Mixing
   https://arxiv.org/abs/2007.08411

9. HarBeat 项目交接与真实部署手册，2026-06-07，用户上传文档 `project(7).md`
