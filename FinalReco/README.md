# FRe Music Lab

FRe Music Lab 是一个基于 Streamlit 的音乐语义检索应用，它把早期 `Rec0` 项目的音频分析 / 向量化能力，与 `SpotifyPortal` 的交互界面整合到了同一个系统里。

它在一个页面中提供 4 个核心工作流：

1. 输入 vibe 描述，先在 Spotify 中召回候选歌曲，再进行语义重排，并把最终结果分析后写入本地数据库。
2. 输入 Spotify 歌单链接，再输入你想要的描述，把歌单向量化存入本地库后，对上传歌单或现有本地库做语义搜索。
3. 直接对当前本地音乐语义数据库做自然语言搜索，返回带 Spotify 封面与跳转链接的结果。
4. 输入 Spotify 歌单链接后自动分析并排歌，先展示 DJ 排序与过渡评分，点击确认后执行快速混音导出。

这个系统的核心思想是：

- 用 Spotify 作为音乐发现和展示层
- 用 CLAP 做文本 / 音频跨模态语义映射
- 用 ChromaDB 做本地向量检索
- 用 Streamlit 做统一交互界面
- 通过不断 ingest 新歌曲，让本地语义库逐渐成长

---

## 一、系统整体逻辑

整个系统可以理解成 5 层：

### 1. 展示层
负责页面布局、输入框、结果卡片、封面、按钮、状态提示。

对应文件：
- `app.py`
- `styles.py`

### 2. Spotify 接入层
负责：
- Spotify 搜索歌曲
- 获取歌曲详情
- 读取歌单内容

对应文件：
- `services/spotify_service.py`

### 3. 文本语义层
负责：
- 把文本描述转成语义向量
- 用文本语义对候选歌曲进行重排

对应文件：
- `services/clap_service.py`
- `services/rerank_service.py`
- `services/vibe_service.py`

### 4. 音频分析与入库层
负责：
- 下载音频
- 计算 BPM / energy
- 生成 CLAP 音频向量
- 写入 ChromaDB

对应文件：
- `services/library_service.py`

### 5. 本地语义检索层
负责：
- 把用户输入描述转成文本向量
- 在 ChromaDB 中对本地歌曲音频向量做最近邻搜索

对应文件：
- `services/search_service.py`

---

## 二、四大工作流说明

## 工作流 1：Vibe recommendation

### 目标
用户输入一句关于氛围、场景、情绪或动作的描述，系统先在 Spotify 中召回歌曲，再做语义重排，然后把最终结果分析并写入本地数据库。

### 执行流程
1. 用户输入 vibe 文本。
2. `interpret_vibe()` 把文本拆成两部分：
   - `search_query`：适合 Spotify 搜索的粗查询
   - `vibe_description`：适合语义排序的细描述
3. `search_tracks()` 去 Spotify 召回候选歌曲。
4. `rerank_tracks()` 对候选歌曲做语义重排。
5. 取前 N 首结果展示。
6. 对展示结果做音频下载、分析、向量化，并写入本地数据库。

### 当前排序方式
当前第一栏的排序主要是：

- 左边：`vibe_description` -> 文本向量
- 右边：`track name + artist` -> 文本向量
- 按相似度排序

也就是说，第一栏目前是 **文本-文本语义排序**，而不是直接用音频向量排序。

### 第一栏的意义
第一栏最重要的作用不只是“推荐”，更是“养库”：

- 一边根据 vibe 推荐歌曲
- 一边把这些歌曲写入本地向量库
- 这样第三栏的能力会越来越强

---

## 工作流 2：Playlist ingest + semantic search

### 目标
用户输入一个 Spotify 歌单链接，再输入一句描述。系统会先把歌单里的歌曲分析后写入本地 collection，然后再对指定 collection 做语义搜索。

### 执行流程
1. 用户输入歌单链接。
2. `fetch_playlist_tracks()` 读取歌单内的歌曲。
3. `ingest_tracks()` 逐首处理歌曲：
   - 下载音频
   - 提取 BPM / energy
   - 生成 CLAP 音频向量
   - 写入 ChromaDB collection
4. 用户同时输入搜索描述。
5. `search_collection()` 将描述转成文本向量，并在选定的 collection 中搜索最相近的歌曲。
6. 最后再用 Spotify API 补全封面和外链信息。

### 当前匹配方式
工作流 2 的匹配方式是：

- 左边：用户描述 -> CLAP 文本向量
- 右边：歌单入库后的歌曲音频 -> CLAP 音频向量
- 使用 ChromaDB 最近邻检索

因此第二栏已经是一个 **文本 -> 音频向量** 的语义检索流程。

---

## 工作流 3：Search local library

### 目标
直接对当前本地数据库做自然语言语义搜索。

### 执行流程
1. 用户输入描述。
2. `search_collection()` 把描述编码成 CLAP 文本向量。
3. 在 ChromaDB 中与本地 collection 中存储的音频向量做最近邻搜索。
4. 返回最相近的结果。
5. 再通过 Spotify ID 拉取封面、专辑名和跳转链接。

### 当前匹配方式
第三栏的排序逻辑是整个系统里最接近“真正音频语义检索”的部分：

- 左边：用户描述 -> CLAP 文本向量
- 右边：本地数据库中的歌曲音频 -> CLAP 音频向量
- 中间：ChromaDB 做向量近邻搜索
- 最终：按 `distance` 从小到大排序

### 注意
第三栏当前**不是**按 BPM / energy 做主排序。

- BPM / energy 只是 metadata
- 主排序依据是音频 embedding 的距离

---

## 工作流 4：Auto DJ plan + mixdown

### 目标
输入 Spotify 歌单后，在“歌单内部”自动完成分析与排歌。系统先展示可解释的排歌顺序与过渡策略，再确认执行混音预览导出。

### 执行流程
1. 输入歌单链接、scene、可选 style ratios、目标长度、目标能量曲线（`target_energy_curve`）。
2. 系统调用 `fetch_playlist_tracks()` 拉取歌单。
3. 系统调用 `ingest_tracks()` 对歌单歌曲做下载与分析，写入本地 collection。
4. 系统调用 `fetch_with_multiplier(..., multiplier=5)` 进行扩容召回（Oversampling），得到更大的候选池。
5. 调用 `DJContextPlanner.generate_plan(..., target_energy_curve=..., explain=True)` 生成排歌结果。
6. 页面展示：
   - Planned order（排歌顺序）
   - Transition scores（每段过渡的 score/strategy/sync_target_bpm/target_energy/selected_energy/fallback_reason）
7. 点击确认后调用 `render_mix_from_plan()` 生成快速混音预览文件：
   - `outputs/dj_mix_preview.mp3`

### 关键说明（当前版本）
- 当前排歌目标是“能量曲线优先”：先贴合 `target_energy_curve`，再兼顾语义/风格，再考虑 BPM/key 平滑度。
- BPM/key 不再是“绝对死路”条件；当平滑过渡不可用时会触发 fallback：
  - `strategy = "Power Drop / Quick Cut"`
- 当 BPM/key 条件较好时会使用：
  - `strategy = "Smooth Blend"`
- `style_ratios` 在第四栏是可选输入：不填也可跑；填写后会参与风格匹配加分。

### 为什么不会再因为“接不住”直接失败
- 旧逻辑：局部 BPM/key 约束过强，容易死路。
- 新逻辑：能量曲线为主目标，过渡层允许 fallback，不会因为某一步没有“完美接轨曲目”就整体失败。

---

## 三、核心匹配逻辑总结

## 1. 第一栏
### 类型
文本 -> 文本

### 排序依据
- 用户 vibe 描述的文本向量
- Spotify 候选歌曲的 `歌名 + 艺人名` 文本向量
- 按相似度从高到低排序

## 2. 第二栏
### 类型
文本 -> 音频

### 排序依据
- 用户描述的文本向量
- 本地 collection 中的音频向量
- 按 Chroma distance 从小到大排序

## 3. 第三栏
### 类型
文本 -> 音频

### 排序依据
- 用户描述的文本向量
- 本地 collection 中的音频向量
- 按 Chroma distance 从小到大排序

---

## 四、第三栏向量匹配详解

这一部分是整个系统中最重要、也最容易误解的地方。

## 第三栏到底在匹配什么？
第三栏不是在做下面这些事情：

- 不是用 `歌名 + 艺人名` 排序
- 不是直接按 BPM 排序
- 不是直接按 energy 排序
- 不是按 Spotify 热度排序

第三栏在做的是：

### 左边
用户输入的自然语言描述，例如：

- “Warm old-school hip-hop with dusty drums and late-night city mood”
- “忧郁、低速、雨夜里适合独自走路的音乐”

系统会把这段文本编码成一个 **CLAP 文本向量**。

对应代码：

```6:13:services/search_service.py
def search_collection(query_text: str, collection_name: str, top_k: int = 10) -> List[dict]:
    collection = create_collection(collection_name)
    query_embedding = encode_texts([query_text])[0].flatten().tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )
```

### 右边
本地数据库中的每首歌曲，在入库时已经被下载音频并做过分析。

系统会对音频本身生成一个 **CLAP 音频向量**。

对应代码：

```24:35:services/library_service.py
    def embed_file(self, audio_path: Path) -> List[float]:
        audio, sample_rate = librosa.load(audio_path, sr=48000, mono=True)
        inputs = self.processor(audio=audio, sampling_rate=sample_rate, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.no_grad():
            audio_features = self.model.get_audio_features(**inputs)
            if hasattr(audio_features, "pooler_output") and audio_features.pooler_output is not None:
                embedding = audio_features.pooler_output.cpu().numpy().flatten().tolist()
```

然后这个音频向量会被写进 ChromaDB：

```128:133:services/library_service.py
        collection.upsert(
            ids=[track["spotify_id"]],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[f"{track['track_name']} - {track['artist']}"]
        )
```

## 匹配过程
第三栏检索时，做的是：

- 文本描述 -> 文本向量
- 本地歌曲音频 -> 音频向量
- ChromaDB 计算最近邻
- 返回距离最近的若干首

所以第三栏本质上是一个 **跨模态语义检索系统**：

- query 是文本模态
- database 是音频模态

## 最终排序依据
最终排序依据是 `distance`：

```15:28:services/search_service.py
    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])
    documents = results.get("documents", [[]])
    rows = []

    for metadata, distance, document in zip(
        metadatas[0] if metadatas else [],
        distances[0] if distances else [],
        documents[0] if documents else [],
    ):
        item = dict(metadata or {})
        item["distance"] = float(distance)
        item["document"] = document
        rows.append(item)

    rows.sort(key=lambda item: item.get("distance", 0.0))
    return rows
```

这意味着：

- `distance` 越小
- 代表 query 文本向量和歌曲音频向量越接近
- 排名越靠前

## BPM / energy 在第三栏中的角色
第三栏会展示：

- BPM
- energy
- collection

但当前这些值只是：

- 用于展示
- 用于理解结果
- 用于后续可扩展排序规则

它们现在**不是第三栏的主排序依据**。

## 如果要修改第三栏逻辑，主要改哪里
如果你后面想自己改第三栏，通常主要看下面几个文件：

- `services/search_service.py`
  - 改查询向量生成方式
  - 改最终排序规则
- `services/library_service.py`
  - 改入库时存什么向量 / 什么特征
- `services/clap_service.py`
  - 改文本编码逻辑
- `app.py`
  - 改第三栏交互方式和展示结果

---

## 五、项目文件结构

```text
FinalReco/
  app.py
  styles.py
  requirements.txt
  .env.example
  .gitignore
  README.md
  services/
    __init__.py
    clap_service.py
    config.py
    dj_planner_service.py
    library_service.py
    mixdown_service.py
    rerank_service.py
    search_service.py
    spotify_service.py
    vibe_service.py
```

---

## 六、主要文件职责

### `app.py`
系统主入口，负责：
- 四栏 UI
- 工作流编排
- 结果展示
- Spotify 封面补全

### `styles.py`
负责：
- 页面主题样式
- hero section
- 卡片组件
- panel header

### `services/config.py`
负责：
- ChromaDB 路径
- 默认 collection 名称
- CLAP 模型名
- Spotify 相关配置常量

### `services/spotify_service.py`
负责：
- Spotify 搜索
- 读取歌单
- 获取单曲详情
- 处理搜索 fallback query

### `services/vibe_service.py`
负责：
- 从 vibe 中提取 genre / year
- 生成 `search_query`
- 生成 `vibe_description`

### `services/clap_service.py`
负责：
- 加载 CLAP 模型
- 文本编码
- 向量归一化

### `services/rerank_service.py`
负责：
- 第一栏候选歌曲的文本语义重排

### `services/library_service.py`
负责：
- 下载音频
- 计算 BPM / energy
- 计算音频向量
- 写入 ChromaDB

### `services/search_service.py`
负责：
- 本地语义搜索
- 返回 distance 和 metadata
- 提供 `fetch_with_multiplier()` 做扩容召回（Oversampling）

### `services/dj_planner_service.py`
负责：
- DJ 上下文建模（scene）
- 基于 BPM / Camelot / energy 的过渡评分
- Beam Search 排歌
- `explain=True` 时输出分层评分

### `services/mixdown_service.py`
负责：
- 按排歌结果下载计划内音频
- 根据 `strategy` 与 `sync_target_bpm` 做快速混音
- 导出混音预览 `outputs/dj_mix_preview.mp3`

---

## 七、环境准备

## 依赖安装

```bash
pip install -r requirements.txt
```

当前依赖包括：

- `streamlit`
- `spotipy`
- `yt-dlp`
- `transformers`
- `torch`
- `librosa`
- `chromadb`
- `python-dotenv`
- `numpy`
- `pydub`（第四栏混音预览）

---

## 环境变量

根据 `.env.example` 创建 `.env`：

```env
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

说明：
- 歌曲搜索和单曲详情使用 client credentials
- 歌单读取使用 OAuth

---

## 八、运行方式

在项目目录执行：

```bash
streamlit run app.py
```

或使用绝对路径：

```bash
streamlit run "d:\RecOO\FRe\FinalReco\app.py"
```

---

## 九、当前系统的优点

- 一个 UI 同时覆盖推荐、入库、检索
- Spotify 负责发现和展示
- 本地库负责真正的音频语义搜索
- 第三栏已经具备文本 -> 音频语义检索能力
- collection 机制让你可以维护不同来源的数据集

---

## 十、当前系统的限制

- 第一栏仍然是文本-文本粗排，不是音频精排
- BPM / energy 当前只是展示字段，没有参与主排序
- 大歌单 ingest 会比较慢
- 当前一次只检索一个 collection
- 依赖 `yt-dlp` 的音源抓取结果
- 第三栏结果好坏依赖本地库规模与质量

---

## 十一、建议的后续增强方向

1. **第一栏升级成二次精排**
   - 先文本粗排
   - 再对 shortlist 做音频向量精排

2. **第三栏加入 BPM / energy 加权排序**
   - 在 `search_service.py` 中加入混合评分

3. **支持跨 collection 联合搜索**
   - 当前只能搜索单个 collection

4. **增加 ingest 进度与失败明细**
   - 提高可用性

5. **增加检索调试信息**
   - 显示 query、distance、召回来源、重排原因

---

## 十二、DJ Planner API 用法（新增）

`services/dj_planner_service.py` 提供了一个规则驱动的 DJ 排序器 `DJContextPlanner`，用于把 `search_service` 返回的候选池（无序）转成可混音的有序播放计划。

### 输入数据要求
每个候选 `row` 最少应包含：

- `spotify_id`（或 `track_id`）
- `distance`（语义距离）
- `metadata.bpm` / `metadata.BPM`
- `metadata.energy`（1-10）
- `metadata.key`（Camelot，如 `8A`）
- `metadata.dominant_styles`（风格标签列表）

### 最小调用示例

```python
from services.search_service import fetch_with_multiplier
from services.dj_planner_service import DJContextPlanner, SessionContext

target_length = 6
style_ratios = {"hiphop": 0.6, "popping": 0.4}

# 1) 扩容召回（Oversampling）
raw_candidates = fetch_with_multiplier(
    collection_name="dj_workbench",
    target_length=target_length,
    style_ratios=style_ratios,
    multiplier=5,
    query_text=None,  # 有语义文本时可传入
)

# 2) 能量曲线驱动排歌
planner = DJContextPlanner()
context = SessionContext(scene_type="party", style_ratios=style_ratios)

plan = planner.generate_plan(
    candidates=raw_candidates,
    context=context,
    target_length=target_length,
    target_energy_curve=[7.0, 7.8, 8.4, 7.6, 8.6, 7.9],
    explain=True,
)
print(plan)
```

### 输出结构
`generate_plan()` 输出固定结构（JSON-friendly）：

- `session_context`
- `ordered_tracks`
- `transitions`

当 `explain=True` 时，每段 transition 会额外包含：

- `explain.target_energy`
- `explain.selected_energy`
- `explain.energy_match`
- `explain.transition_score`
- `explain.strategy`
- `explain.strategy_reason`

并在顶层追加 `planner_debug`，用于查看 beam 参数、候选池规模和实际能量曲线。

### 调参入口
可直接修改 `DJContextPlanner` 类常量：

- `W1` / `W2` / `W3`：能量匹配 / 语义风格 / 过渡平滑的权重
- `BEAM_WIDTH`：Beam 搜索宽度
- `BPM_SMOOTH_THRESHOLD`：Smooth Blend 的 BPM 相对差阈值（默认 6%）

### 当前策略（能量优先 + 兜底）
`generate_plan()` 当前行为：

1. 先按 `target_energy_curve` 逐步挑歌（Energy-first）。
2. 每步计算过渡策略：
   - 平滑可连：`Smooth Blend`
   - 不平滑但能量匹配高：`Power Drop / Quick Cut`（fallback）
3. 不会因为单步无法完美 beatmatch 而整体失败。

---

## 十三、一句话总结

FRe Music Lab 是一个将 Spotify 发现能力、CLAP 文本/音频跨模态语义能力、ChromaDB 本地向量检索能力和 Streamlit 四工作流交互界面整合起来的系统：既能推荐与检索音乐，也能按能量曲线自动排歌并输出混音预览。
