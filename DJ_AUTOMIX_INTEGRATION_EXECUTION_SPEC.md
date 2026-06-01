# HarBeat DJ Automix 鍏ㄩ摼璺泦鎴愭墽琛岃鏍?
鐗堟湰锛歏1.0
鏃ユ湡锛?026-06-01
璇昏€咃細鍚庣宸ョ▼甯堛€丗lutter 宸ョ▼甯堛€丷K3588 宸ョ▼甯堛€丣etson 宸ョ▼甯堛€佹祴璇曚汉鍛樸€佸悗缁?AI Agent
鐘舵€侊細鍙墽琛岃鏍笺€傛寜闃舵瀹炴柦锛屾瘡闃舵鍗曠嫭鎻愪氦銆?

---

## 0. 鏂囨。鐢ㄩ€?
杩欎唤鏂囨。鍥炵瓟涓や釜闂锛?
1. HarBeat 浠庨€夋瓕銆佸垎鏋愭瓕鏇层€佸鎵炬贩闊崇墖娈点€侀€夋嫨娣烽煶鏂规硶鍒?RK3588 鍙戝０锛屽凡缁忓仛鍒板摢涓€姝ャ€?2. 鍚屼簨鎴栧彟涓€涓?AI Agent 搴旇鎸変粈涔堥『搴忔妸鐜版湁浠ｇ爜鏀舵暃鎴愪竴鏉＄ǔ瀹氥€佸彲璇曞惉銆佸彲閮ㄧ讲鐨勮嚜鍔ㄦ贩闊抽摼璺€?
鏈鏍间笉鏄姛鑳芥効鏈涙竻鍗曘€傛枃妗ｄ腑鐨勪换鍔￠兘瀵瑰簲褰撳墠浠撳簱銆佽繙绔垎鏀垨宸茬‘璁ょ殑缂哄彛銆?
鏈疆瀹¤鍩轰簬浠ヤ笅浠ｇ爜蹇収锛?
| 绫诲瀷 | 鍒嗘敮鎴栨枃浠?| 鐢ㄩ€?|
|------|------------|------|
| 褰撳墠涓荤嚎 | `origin/codex/dev-flutter-native-mobile`锛孒EAD `24513bc` | 褰撳墠绋冲畾鍩哄簳 |
| 鎺ㄨ崘闆嗘垚鍏ュ彛 | `origin/codex/integrate-analysis-session`锛孒EAD `f19040e` | 鍚屼簨鏁寸悊鍚庣殑鏂板姛鑳藉叆鍙?|
| 鍘熷 DJ Set 鍒嗘敮 | `origin/codex/dj-set-pipeline-deploy`锛孒EAD `83f98b7` | 浠呯敤浜庤拷婧紝涓嶇洿鎺ュ悎骞?|
| 鐙珛 RK 瀹為獙鍒嗘敮 | `origin/codex/rk3588-edge-prefetch-and-stem-fixes`锛孒EAD `5508a73` | 浠呴€夋嫨鎬хЩ妞嶏紝涓嶆暣鍒嗘敮鍚堝苟 |
| 鏃ц瀺鍚堣鏄?| `docs/MERGE_PLAN.md` | 鍙傝€冩潗鏂欙紝涓嶈兘鏈烘鐓у仛 |
| 浜у搧鎬昏鏍?| `docs/DEVELOPMENT_SPEC.md` | 浜у搧杈圭晫鍜岀‖浠舵柟鍚戠殑涓婁綅鏂囨。 |

### 0.1 鏍稿績鍒ゆ柇

褰撳墠绯荤粺宸茬粡鎷ユ湁澶ч儴鍒嗙Н鏈紝浣嗛摼璺繕娌℃湁鏀跺彛锛?
- C1 闊充箰鍒嗘瀽宸茬粡鑳戒骇鍑?BPM銆乥eatgrid銆乸hrase銆丩UFS銆乻tems 娲昏穬搴﹀拰瀹夊叏绐楀彛銆?- 鏂拌繙绔垎鏀凡缁忚兘鍋氭洸搴撶骇 pair matrix銆乥eam search 鎺掓瓕鍜屼簲绉?Set 妯℃澘銆?- App 宸茬粡寮€濮嬩紶閫?`tempo_ratio`銆乣stem_curves`銆侀鐑拰鑺傛媿寮哄寲鎸囦护銆?- RK 褰撳墠闆嗘垚鍒嗘敮鍙互鍚屾绱犳潗銆佸弻 deck 鎾斁銆侀鍙栥€佹櫘閫氳浆鍦恒€侀儴鍒?stem-aware 杞満锛屽苟鍥炰紶 `playback_tier`銆?
鐪熸鐨勯棶棰樻槸锛氬垎鏋愩€佽瘎鍒嗐€丄pp 灞曠ず鍜?RK 鎵ц杩樻病鏈変娇鐢ㄥ悓涓€浠借浆鍦鸿鍒掋€傜畻娉曠湅璧锋潵鍦ㄥ仛 DJ 鍐崇瓥锛屾壃澹板櫒涓嶄竴瀹氭墽琛屼簡閭ｄ唤鍐崇瓥銆?
---

## 1. 浠?DJ 鎿嶄綔绗竴鎬у師鐞嗗畾涔夌郴缁?
鑷姩娣烽煶涓嶆槸鈥滈殢鏈洪€変竴绉嶈浆鍦烘晥鏋溾€濄€備竴鍚?DJ 鍦ㄦ帴姝屾椂锛屽疄闄呭湪澶勭悊浜斾欢浜嬶細

1. 涓嬩竴棣栨挱浠€涔堬細瀹冩槸鍚﹂€傚悎鐜板満鍦烘櫙銆佽垶绉嶃€佸綋鍓嶈兘閲忓拰鍚庣画鍙欎簨銆?2. 浠€涔堟椂鍊欓€€鍑?A锛氬簲钀藉湪 bar 鎴?phrase 杈圭晫锛屼笉鑳芥妸涓€鍙ヤ汉澹般€佷竴娈甸紦寰幆鎴栦竴涓?build-up 浠庝腑闂寸爫鏂€?3. 浠?B 鐨勫摢閲岃繘鍏ワ細涓嶈兘榛樿浠庢枃浠跺紑澶存挱鏀俱€傞渶瑕佹壘 clean intro銆佷富 groove銆乨rop 鎴栧畨鍏?cue銆?4. 鎬庝箞浜ゆ帴鎺у埗鏉冿細鑺傚銆佷綆棰戙€佷汉澹般€佹棆寰嬪拰鎬讳綋鍝嶅害闇€瑕佹寜椤哄簭浜ゆ帴銆?5. 濡傛灉鏉′欢涓嶅濂芥€庝箞鍔烇細娌℃湁 stems銆乥eatgrid 浣庣疆淇″害銆丅PM 宸窛澶ф垨绱犳潗鏈紦瀛樻椂锛屽繀椤昏嚜鍔ㄩ檷绾с€?
HarBeat 鐨?P0 鐩爣涓嶆槸澶嶅埗涓撲笟 DJ 鍙般€傜郴缁熻礋璐ｅ鏉傛妧鏈姩浣滐紝鐢ㄦ埛鍙〃杈炬剰鍥撅細

- 涓嬩竴棣?- 鑳介噺鏇撮珮鎴栨洿绋?- 寤堕暱褰撳墠娈佃惤
- Talk
- 鎾ら攢
- 鎬婚煶閲?
婊ゆ尝鍣ㄣ€丒Q銆乻tem gain銆乼empo 鎷変几銆乪cho 鍜屽叿浣撴帴姝岀偣灞炰簬绠楁硶涓?RK 闊抽寮曟搸銆?
---

## 2. 鐩爣鏋舵瀯

```mermaid
flowchart LR
  Import["鎺堟潈闊虫簮瀵煎叆"] --> Jetson["Jetson 鍒嗘瀽涓?stems 鏈嶅姟"]
  Jetson --> Analysis["TrackAnalysisV2"]
  Analysis --> Planner["Set Planner + Transition Candidate Scorer"]
  Planner --> Plan["MixPlanV2"]
  Plan --> Sync["RK sync-worker"]
  Plan --> App["Flutter App"]
  Sync --> Cache["RK 鏈湴 cache"]
  App --> Edge["RK edge-agent"]
  Controller["瀹炰綋鎰忓浘鎺у埗鍣?] --> Edge
  Edge --> Engine["RK audio-engine"]
  Cache --> Engine
  Engine --> Output["闊冲搷"]
  Engine --> Edge
  Edge --> Events["SessionEvent 鎸佷箙鍖?]
```

### 2.1 鍥涚鑱岃矗

| 绔?| 璐熻矗浠€涔?| 涓嶈礋璐ｄ粈涔?|
|----|----------|------------|
| Jetson | 閲嶅垎鏋愩€丏emucs銆佺粨鏋勫寲闊充箰璧勪骇銆乵anifest | 涓嶆壙鎷呯幇鍦轰綆寤惰繜鎾斁 |
| RK3588 | 鏈湴缂撳瓨銆佸疄鏃跺弻 deck銆丏SP銆乻tem automation銆佺绾垮厹搴?| 涓嶈窇 Demucs 绾ч噸鍒嗘瀽 |
| Flutter App | 璧涘墠缂栨帓銆佺姸鎬佹樉绀恒€佺幇鍦烘剰鍥俱€佽澶囨帶鍒?| 涓嶉噸鏂板彂鏄庝竴濂?planner锛屼笉浣滀负 P0 闊抽涓绘満 |
| 浜戠缃戝叧 | 鐧诲綍銆佽繙绋嬭闂€佹暟鎹悓姝ャ€佷簨浠舵寔涔呭寲 | 涓嶈繘鍏ョ幇鍦哄疄鏃堕煶棰戦棴鐜?|

### 2.2 涓€鏉′笉鍙牬鍧忕殑杈圭晫

涓€娈佃浆鍦哄彧鑳芥湁涓€浠芥潈濞佽鍒掋€?

璇勫垎銆丄pp 棰勮銆丄pp 涓嬪彂銆乪dge-agent 杞彂鍜?audio-engine 鎵ц蹇呴』寮曠敤鍚屼竴涓?`transition_id` 鍜屽悓涓€浠?`TransitionCandidate`銆傜幇鍦哄彲浠ュ仛鑳藉姏鏍￠獙鍜屽畨鍏ㄩ檷绾э紝浣嗕笉鑳介噸鏂伴€夊彟涓€涓贩鍏ョ偣銆?
---

## 3. 褰撳墠瀹炵幇绋嬪害鎬昏

鐘舵€佸畾涔夛細

| 鐘舵€?| 鍚箟 |
|------|------|
| 宸插疄鐜?| 褰撳墠浠ｇ爜瀛樺湪锛屾帴鍙ｅ熀鏈彲鐢?|
| 閮ㄥ垎瀹炵幇 | 鏍稿績閫昏緫瀛樺湪锛屼絾绮惧害銆佹祴璇曟垨閮ㄧ讲浠嶉渶琛ラ綈 |
| 鏈疮閫?| 鏌愪竴灞傚凡鏈変唬鐮侊紝浣嗘病鏈夎繘鍏ユ渶缁堟挱鏀鹃摼 |
| 鏈疄鐜?| 浠嶉渶鏂板 |

### 3.1 绔埌绔祦绋嬬洏鐐?
| 闃舵 | 褰撳墠鐘舵€?| 宸茬粡鍋氬埌浠€涔?| 涓昏缂哄彛 |
|------|----------|--------------|----------|
| 1. 瀵煎叆鎺堟潈姝屾洸 | 閮ㄥ垎瀹炵幇 | 鏇插簱 API銆佷笂浼犮€佸垎鏋愬拰 stems 鍒嗙鍏ュ彛宸插瓨鍦?| 闇€瑕佺粺涓€瀵煎叆鍚庣殑鍒嗘瀽鐘舵€佹満鍜屽け璐ラ噸璇?|
| 2. 鍗曟洸鍩虹鍒嗘瀽 | 宸插疄鐜?| BPM銆丅PM 鏇茬嚎銆乼empo 绋冲畾搴︺€乥eatgrid銆乨ownbeat銆佹媿鍙枫€乲ey銆丆amelot銆丩UFS銆佽兘閲忔洸绾裤€乸hrase map | 闇€瑕佷汉宸ユ牎鍑嗛泦鍜岀浜屽垎鏋愬紩鎿庝氦鍙夐獙璇?|
| 3. Stems 鍒嗘瀽 | 閮ㄥ垎瀹炵幇 | Demucs 鍥涜建銆乤ctivity windows銆乻tem quality 鍘熷瀷銆乿ocal events銆乥ass risk銆乮ntro / outro clean score | 闃堝€间粛闇€鐢ㄧ湡瀹炴洸搴撴牎鍑?|
| 4. 鎵惧崟鏇插畨鍏ㄦ贩鍏?/ 娣峰嚭鐗囨 | 閮ㄥ垎瀹炵幇 | C1 宸茶緭鍑?`transition_windows[]` 鍜?hot cues锛涙柊 DJ Set 鍒嗘敮涔熶細鐢熸垚 safe entry / exit | 涓ゅ閫昏緫娌℃湁缁熶竴锛涜繙绔?scorer 浣跨敤浜嗙畝鍖?proxy |
| 5. 閫変笅涓€棣?| 閮ㄥ垎瀹炵幇 | 褰撳墠涓荤嚎鏈?CandidateSelector锛涜繙绔湁 pair matrix銆佽鑹插垎绫汇€佷簲绉?Set 妯℃澘鍜?beam search | 闇€瑕佺粺涓€涓轰竴涓?set planner锛屽苟浣跨敤鐪熷疄 C1 鏁版嵁 |
| 6. 涓?A->B 閫夋嫨鎺ユ瓕鏂规 | 閮ㄥ垎瀹炵幇 | 褰撳墠鏈?`stem_automix.py` preset 搴撱€佽繙绔湁 `mixer_rules.py` 鍜?TransitionSpec銆丷K 鏈?fallback planner | scorer 璇勫垎鐨勭獥鍙ｄ笌鏈€缁堟墽琛岀獥鍙ｅ彲鑳戒笉鍚?|
| 7. App 灞曠ず鍜屼笅鍙?| 鏈疮閫?| App 鍙互灞曠ず Set锛岃皟鐢?`/xfade`锛屽苟灏濊瘯涓嬪彂 tempo 鍜?stem curves | App 閫変腑 Set 鍚庝涪寮?`plans[]`锛岀幇鍦哄啀娆¤皟鐢ㄦ棫 pair planner |
| 8. RK 绱犳潗鍚屾 | 閮ㄥ垎瀹炵幇 | manifest 涓嬭浇銆乷riginal + stems銆乻ize / sha256銆佹牸寮忎繚鐣欍€佽秴鏃堕檷绾?| sidecar 缂撳瓨鏍￠獙瀛樺湪闄堟棫鏂囦欢璇垽椋庨櫓 |
| 9. RK 瀹炴椂鎾斁 | 閮ㄥ垎瀹炵幇 | 鍙?deck銆佹櫘閫氳浆鍦恒€乻tem-aware / non-stem tier銆乸refetch銆佺姸鎬佸洖浼?| 闆嗘垚鍒嗘敮浼氫涪寮?`tempo_ratio` 鍜?`stem_curves`锛涚己灏戜袱涓?App 宸茶皟鐢ㄦ帴鍙?|
| 10. Session 鐜板満缂栨帓 | 鍘熷瀷 | 鐘舵€佹満銆侀槦鍒椼€佸畨鍏ㄦ睜銆佹挙閿€鏍堛€佹湰鍦?Coordinator 宸插瓨鍦?| 灏氭湭鎴愪负鍞竴璋冨害鍏ュ彛锛涙湰鍦版柊 helper 鏈帴鍏ュ疄闄呭垎鏀?|
| 11. 鍙嶉瀛︿範 | 鏈疄鐜?| RK 浼氭殏瀛樹簨浠跺苟灏濊瘯 flush | 浜戠 RK event 鎺ュ彛鍙墦鍗版棩蹇楋紝娌℃湁鐪熸鎸佷箙鍖?|
| 12. 瀹炰綋鎺у埗鍣?| 鍘熷瀷 | USB 涔濋敭鍜?HTTP trigger 璺緞瀛樺湪 | P0 鍏帶浠朵骇鍝佸崗璁€佸浐浠跺拰瀹炰綋鏍锋満浠嶉渶瀹炵幇 |

---

## 4. 褰撳墠宸插疄鐜拌兘鍔涜琛?
## 4.1 姝屾洸鍒嗘瀽锛氱幇鍦ㄥ凡缁忓垎鏋愬摢浜涘唴瀹?
涓诲叆鍙ｏ細`app/modules/library/analysis.py::analyze_audio_file()`
stems 鍚庡鐞嗭細`app/modules/library/stem_analysis.py`銆乣app/modules/library/background_tasks.py`

| 鍒嗘瀽椤?| 杈撳嚭瀛楁 | 褰撳墠鍋氭硶 | 瀹屾垚搴﹀垽鏂?|
|--------|----------|----------|------------|
| 鏂囦欢鏃堕暱 | `duration` | 璇诲彇鐪熷疄闊抽鍏冩暟鎹?| 宸插疄鐜?|
| BPM | `bpm` | `librosa.beat.beat_track` | 宸插疄鐜帮紝闇€鏍″噯 |
| BPM 鏇茬嚎 | `bpm_curve[]` | 婊戝姩鑺傛媿绐楀彛璁＄畻灞€閮?BPM | 宸插疄鐜拌鍒欑増 |
| Tempo 绋冲畾搴?| `tempo_stability` | 姹囨€?BPM 鏇茬嚎娉㈠姩 | 宸插疄鐜拌鍒欑増 |
| Beatgrid | `beat_points[]`銆乣beat_grid_interval`銆乣beat_needs_review` | beat tracker + 璐ㄩ噺鎽樿 | 宸插疄鐜?|
| Downbeat | `downbeats[]` | 涓庢媿鍙蜂娇鐢ㄥ悓涓€缁?beat accent 璇佹嵁鑱斿悎鎺ㄦ柇 | 宸插疄鐜拌鍒欑増 |
| 鎷嶅彿 | `time_signature` | 鑱斿悎鎺ㄦ柇锛涜瘉鎹急鏃跺洖閫€ 4/4 骞舵爣璁板鏍?| 宸插疄鐜板畨鍏ㄧ増 |
| 璋冩€?| `key`銆乣camelot_key`銆乣key_profile` | CQT + CENS + 妯℃澘鍖归厤 | 宸插疄鐜?|
| 鍏ㄦ洸鑳介噺 | `energy` | RMS 褰掍竴鍖?| 宸插疄鐜?|
| 鍒嗘鑳介噺 | `energy_curve[]` | 鏃堕棿绐楀彛鑳介噺鏇茬嚎 | 宸插疄鐜?|
| LUFS 鍜屽嘲鍊?| `loudness_profile` | 鍝嶅害銆乺eplay gain銆乧lipping risk | 宸插疄鐜?|
| 涔愭缁撴瀯 | `cue_points[]`銆乣phrase_map[]` | novelty銆乨ownbeat銆?-bar 鍒嗙粍鍜岃兘閲?| 宸插疄鐜拌鍒欑増 |
| 娈佃惤寮哄害 | phrase 涓殑 `intensity`銆乣is_peak_section` | 鑳介噺鍜岄煶鑹茶鍒?| 宸插疄鐜拌鍒欑増 |
| Groove | `groove` | 鑺傛媿绋冲畾搴︺€乻alience 绛夎鍒?| 宸插疄鐜拌鍒欑増 |
| Danceability | `danceability_score` | groove銆侀紦鐐瑰拰鑳介噺鐨勫彲瑙ｉ噴瑙勫垯 | 宸插疄鐜拌鍒欑増 |
| 鑸炴睜鐢诲儚 | `dancefloor_profile` | physical energy銆乼ension銆乸eakness銆乫atigue risk | 宸插疄鐜拌鍒欑増 |
| Mood | `dancefloor_profile.mood_tags[]` | 瑙勫垯鏍囩 | 宸插疄鐜拌鍒欑増 |
| 瀹夊叏杞満绐楀彛 | `transition_windows[]` | phrase銆佽兘閲忓拰浣嶇疆瑙勫垯锛泂tems 鍚庡寮?| 宸插疄鐜拌鍒欑増 |
| Hot cues | `dj_hot_cues[]` | intro end銆乵ain groove銆乫irst drop銆乥est loop銆乷utro start | 宸插疄鐜拌鍒欑増 |
| 杞満寤鸿 | `transition_recommendations[]` | 鎸変箰娈电粰鍑?mix-in / mix-out 寤鸿 | 宸插疄鐜拌鍒欑増 |

### 4.1.1 Stems 鍚庡鐞?
| 鍒嗘瀽椤?| 杈撳嚭瀛楁 | 褰撳墠鍋氭硶 | 瀹屾垚搴﹀垽鏂?|
|--------|----------|----------|------------|
| 鍥涜建鍒嗙 | `stems.vocals/drums/bass/other` | Jetson 杩愯 Demucs | 宸插疄鐜?|
| 娲昏穬绐楀彛 | `stem_activity_windows[]` | 姣忎釜绐楀彛缁熻鍥涜建鑳介噺 | 宸插疄鐜?|
| Stem 璐ㄩ噺 | `stem_quality_score`銆乣stem_quality_profile` | 瀹屾暣鎬у拰閲嶅缓璇樊 proxy | 閮ㄥ垎瀹炵幇 |
| 浜哄０杩涘叆閫€鍑?| `vocal_events[]` | vocals 娲昏穬绐楀彛杈规部妫€娴?| 宸插疄鐜拌鍒欑増 |
| Bass 椋庨櫓 | `bass_risk_windows[]` | bass 娲昏穬搴﹀拰浣庨鍔熺巼 | 宸插疄鐜拌鍒欑増 |
| Intro 骞插噣搴?| `intro_clean_score`銆乣intro_is_clean` | vocals銆乥ass銆乨rums 娲昏穬搴?| 閮ㄥ垎瀹炵幇 |
| Outro 骞插噣搴?| `outro_clean_score`銆乣outro_is_clean` | vocals銆乥ass銆乨rums 娲昏穬搴?| 閮ㄥ垎瀹炵幇 |

### 4.1.2 鍒嗘瀽灞傜殑鐪熷疄杈圭晫

鐜板湪鐨?C1 宸茬粡瓒冲鏀寔绗竴鐗堣嚜鍔ㄦ贩闊筹紝浣嗚繕涓嶈兘瀹ｇО杈惧埌 djay 鎴?rekordbox 鐨勬垚鐔熷害锛?
- BPM 鍙湁涓€涓富鍒嗘瀽寮曟搸锛屾病鏈?madmom銆丒ssentia 鎴栦汉宸?grid 澶嶆牳闂幆銆?- 闈?4/4銆佺湡浜洪紦鍜屽眬閮ㄥ彉閫熸洸鐩粛闇€瑕?`needs_review`銆?- Mood銆侀鏍煎拰 danceability 涓昏鏄彲瑙ｉ噴瑙勫垯锛屼笉鏄缁冨悗鐨勬ā鍨嬨€?- Stem quality 鑳藉彂鐜版槑鏄鹃棶棰橈紝浣嗚繕涓嶈兘绋冲畾璇嗗埆浜哄０娈嬬暀銆佺灛鎬佹崯鍧忓拰浼奖銆?- 鎵€鏈夐槇鍊奸兘闇€瑕佷娇鐢?100 鍒?300 棣栦汉宸ユ爣娉ㄦ洸鐩牎鍑嗐€?
## 4.2 鎵鹃€傚悎娣烽煶鐨勭墖娈碉細鐜板湪鍋氬埌浠€涔堢▼搴?
褰撳墠鏈変袱濂楁潵婧愶細

1. 涓荤嚎 C1锛歚transition_windows[]`銆乣dj_hot_cues[]` 鍜?`transition_recommendations[]`銆?2. 杩滅 DJ Set 鍒嗘敮锛歚app/modules/dj_set/track_profiler.py` 鐢熸垚 safe entry / exit锛宍edge_analyzer.py` 瀵?A->B 璇勫垎銆?
宸茬粡鑳藉仛锛?
- 浼樺厛鍦?phrase銆乨ownbeat銆乷utro銆乥reak銆乿erse銆乧horus 鍜?drop 闄勮繎鎵惧€欓€変綅缃€?- 閬垮厤鏂囦欢灏鹃儴鍓╀綑鏃堕棿澶煭瀵艰嚧娣″嚭琚埅鏂€?- 鍦ㄦ湁 stems 鏃跺垽鏂汉澹板拰浣庨椋庨櫓銆?- 鍦ㄦ病鏈?stems 鏃朵繚鐣?non-stem fallback銆?
浠嶆湁涓€涓繀椤讳慨澶嶇殑闂锛?
- `edge_analyzer.py` 璇勫垎鐨勬槸涓€涓€欓€?entry / exit銆?- `app/modules/dj_set/transition_plan.py` 鍙妸 `edge.exit_time` 浼犵粰 `mixer_rules.build_transition_spec()`銆?- `mixer_rules.py` 浼氬啀娆＄嫭绔嬪鎵?entry / exit銆?
缁撴灉鏄?scorer 璁や负瀹夊叏鐨勭獥鍙ｏ紝涓嶄竴瀹氭槸鎵０鍣ㄧ湡姝ｄ娇鐢ㄧ殑绐楀彛銆傜儫闆炬祴璇曚腑宸茬粡瑙傚療鍒帮細edge 璇勫垎鍏ュ彛涓?`71.667s`锛屽疄闄呰鍒掑叆鍙ｅ彉鎴?`2.4s`銆?
## 4.3 閫夋瓕鍜屾帓姝岋細鐜板湪鍋氬埌浠€涔堢▼搴?
### 褰撳墠涓荤嚎

`app/modules/session/candidate_selector.py` 宸茬粡鍙互鏍规嵁鍦烘櫙銆乨anceability銆佽兘閲忋€丅PM / key 鐩稿鎬с€侀噸澶嶆儵缃氬拰瀹夊叏椋庨櫓鎸戦€変笅涓€棣栥€?
鏈湴鏈彁浜ゅ師鍨?`app/modules/session/scene_playlist.py` 宸茬粡鍙互鎸夊満鏅敓鎴?warmup銆乥uild銆乸eak銆乺ecover 绛夐樁娈靛紡鑳介噺鏇茬嚎銆?
### 杩滅鏂板鑳藉姏

鎺ㄨ崘闆嗘垚鍒嗘敮鏂板 `app/modules/dj_set/`锛?
| 鏂囦欢 | 浣滅敤 |
|------|------|
| `track_profiler.py` | 鎶婃瓕鏇叉暣鐞嗕负 Set planner profile |
| `role_classifier.py` | 鍒ゆ柇 warmup銆乬roove銆乸eak銆亀eapon 绛夎鑹?|
| `edge_analyzer.py` | 涓烘墍鏈?A->B 寤?pair matrix |
| `set_templates.py` | 瀹氫箟浜旂 Set 鍙欎簨妯℃澘 |
| `set_optimizer.py` | beam search 閫夋嫨姝屾洸椤哄簭 |
| `purpose_planner.py` | 缁欐瘡涓€娈垫帴姝屽垎閰嶇洰鐨?|
| `transition_plan.py` | 鐢熸垚姣忎竴娈佃浆鍦鸿鍒?|
| `quality_gate.py` | 妫€鏌ユ暣濂?Set 鏄惁鏈夋槑鏄鹃棶棰?|
| `service.py` | 涓茶捣瀹屾暣娴佺▼ |

杩欐槸涓€娆℃湁浠峰€肩殑鍗囩骇銆傚畠浠庘€滃彧鍒ゆ柇涓嬩竴棣栤€濆墠杩涘埌鈥滃厛鑰冭檻鏁村満鑳介噺寮э紝鍐嶅垽鏂浉閭绘瓕鏇插叧绯烩€濄€?
浣嗚繙绔?profile 浠嶆湁 proxy锛?
- `track_profiler.py` 鐢?phrase 鏍囩浼扮畻 vocal density锛屾病鏈変紭鍏堣鍙栫湡瀹?`stem_activity_windows[]`銆?- stems 鏂囦欢瀛樺湪灏辨寜璐ㄩ噺 `1.0` 澶勭悊锛屾病鏈変紭鍏堣鍙?C1 鐨?`stem_quality_score`銆?- Set smoke 涓笉灏戞瓕鏇茶鍒や负 `weapon`锛岃鑹查槇鍊奸渶瑕佺湡瀹炴洸搴撴牎鍑嗐€?
缁撹锛氫繚鐣?beam search 楠ㄦ灦锛屾浛鎹?profile 鐨勪簨瀹炴潵婧愩€?
## 4.4 娣烽煶鏂规閫夋嫨锛氱幇鍦ㄥ仛鍒颁粈涔堢▼搴?
褰撳墠鏈変笁濂椾簰琛ヨ兘鍔涳細

| 妯″潡 | 宸叉湁鑳藉姏 | 搴斾繚鐣欑殑鑱岃矗 |
|------|----------|--------------|
| `app/modules/playlists/stem_automix.py` | stem-aware 鍜?non-stem preset銆乤utomation curve銆侀闄╄瘎鍒?| 鐢熸垚鍙墽琛?automation |
| `app/modules/dj_control/mixer_rules.py` | phrase / downbeat 閫夌偣銆丷AW fallback銆乀ransitionSpec | 鐢熸垚缁撴瀯鍖?spec 鍜岃鍒欏瀷鍏滃簳 |
| `cypher-integration/rk3588-edge/audio-engine/transition_planner.py` | RK 渚?style selector銆乸layback tier | RK 鏈湴瀹夊叏闄嶇骇 |

宸茬粡瑕嗙洊鐨勪富瑕佽浆鍦猴細

- 鏅€氾細`fade`銆乣blend`銆乣filter`銆乣echo_freeze`銆乣rise`銆乣melt`銆乣cut`銆乣slam`
- Stems锛歚vocal_handoff`銆乣bass_swap`銆乣drum_swap`銆乣vocal_ducking`銆乣instrumental_only`銆乣vocal_solo_intro`
- 鏇翠赴瀵岀殑棰勮搴擄細`neural_fade`銆乣neural_echo_out`銆乣harmonic_sustain`銆乣loop_bridge`銆乣breakdown_drop` 绛?
褰撳墠鏈€澶ч棶棰樹笉鏄璁炬暟閲忥紝鑰屾槸瀛樺湪澶氫釜 selector锛?
- Set planner 閫変竴娆°€?- `mixer_rules.py` 鍐嶉€変竴娆¤繘鍑虹偣銆?- App 涓㈠純 Set 鐨?`plans[]` 鍚庡張璋冪敤鏃?pair planner銆?- RK 鏀跺埌 style 鍚庤繕浼氭寜鏈湴鑳藉姏闄嶇骇銆?
姝ｇ‘鏂瑰悜涓嶆槸缁х画鍫?preset锛岃€屾槸寤虹珛涓€浠芥潈濞?`TransitionCandidate`锛屾墍鏈夌鍙秷璐瑰畠銆?
## 4.5 鎵ц閾撅細鐜板湪鍋氬埌浠€涔堢▼搴?
### 宸茬粡鍙敤

RK 褰撳墠闆嗘垚鍒嗘敮鏀寔锛?
- `/load_plan`
- `/play`
- `/pause`
- `/resume`
- `/next`
- `/xfade`
- `/prefetch`
- `/trigger`
- `/state`
- `/health`
- `playback_tier = basic | non_stem | stem_aware`
- sync-worker 涓嬭浇 original 鍜?stems
- 鍙?deck 鍜屽熀纭€ DSP

### 灏氭湭璐€?
App 宸茬粡鍚?`/xfade` 鍙戦€侊細

```json
{
  "to_song_id": "uuid",
  "fade_sec": 8.0,
  "to_at_sec": 32.0,
  "style": "vocal_handoff",
  "tempo_ratio": 1.018,
  "stem_curves": {}
}
```

浣嗛泦鎴?RK 鐨?`XfadeRequest` 鍙帴鏀跺墠鍥涗釜瀛楁銆俙tempo_ratio` 鍜?`stem_curves` 琚潤榛樹涪寮冦€?
App 杩樹細璋冪敤锛?
- `/prewarm_beatmatch`
- `/beat_reinforce`

杩欎袱涓帴鍙ｅ彧瀛樺湪浜庣嫭绔?RK 瀹為獙鍒嗘敮锛屾病鏈夎繘鍏ユ帹鑽愰泦鎴愬垎鏀€?
缁撹锛氬綋鍓嶆壃澹板櫒鑳藉惉瑙佸熀纭€杞満鍜岄儴鍒?RK 鍐呭缓 stem-aware style锛屼絾涓嶈兘淇濊瘉鎵ц App 灞曠ず鐨勫畬鏁?DSP 璁″垝銆?
---

## 5. 蹇呴』寤虹珛鐨勭粺涓€鏁版嵁缁撴瀯

## 5.1 `TrackAnalysisV2`

Jetson 鍜屼簯绔暟鎹簱淇濆瓨瀹屾暣浜嬪疄銆俻lanner 涓嶅啀鑷繁鐚滄祴宸叉湁瀛楁銆?
```json
{
  "schema_version": "track-analysis-v2",
  "track_id": "uuid",
  "title": "Song title",
  "artist": "Artist",
  "duration_sec": 213.4,
  "analysis_version": "2026-06-01.1",
  "evidence_level": "measured",
  "bpm": 102.4,
  "bpm_confidence": 0.91,
  "bpm_curve": [
    {"start_sec": 0.0, "end_sec": 16.0, "bpm": 102.3, "stability": 0.95}
  ],
  "tempo_stability": 0.94,
  "beat_points": [0.52, 1.10],
  "downbeats": [0.52, 2.86],
  "time_signature": {
    "numerator": 4,
    "denominator": 4,
    "confidence": 0.84,
    "needs_review": false
  },
  "camelot_key": "8A",
  "key_confidence": 0.82,
  "energy": 0.67,
  "energy_curve": [],
  "loudness_profile": {
    "integrated_lufs": -10.7,
    "peak_dbfs": -0.9,
    "replay_gain_db": -2.1,
    "clipping_risk": false
  },
  "phrase_map": [],
  "transition_windows": [],
  "dj_hot_cues": [],
  "dancefloor_profile": {},
  "genre_profile": {},
  "stems": {
    "available": true,
    "complete": true,
    "quality_score": 0.78,
    "quality_profile": {},
    "activity_windows": [],
    "vocal_events": [],
    "bass_risk_windows": []
  },
  "files": {
    "original": {"url": "https://gateway.example/api/stream/song-id", "size": 123, "sha256": "sha256hex", "format": "mp3"},
    "stems": {
      "vocals": {"url": "https://gateway.example/api/stream/song-id/stem/vocals", "size": 123, "sha256": "sha256hex", "format": "mp3"},
      "drums": {"url": "https://gateway.example/api/stream/song-id/stem/drums", "size": 123, "sha256": "sha256hex", "format": "mp3"},
      "bass": {"url": "https://gateway.example/api/stream/song-id/stem/bass", "size": 123, "sha256": "sha256hex", "format": "mp3"},
      "other": {"url": "https://gateway.example/api/stream/song-id/stem/other", "size": 123, "sha256": "sha256hex", "format": "mp3"}
    }
  }
}
```

绾︽潫锛?
- `evidence_level` 鍙兘鏄?`measured`銆乣proxy` 鎴?`needs_review`銆?- 濡傛灉鐪熷疄瀛楁瀛樺湪锛宲lanner 绂佹浣跨敤 proxy 瑕嗙洊銆?- stems 涓嶅畬鏁存椂浠嶄繚鐣?original锛岃嚜鍔ㄨ蛋 non-stem銆?
## 5.2 `TransitionCandidate`

姣忎竴涓€欓€夐兘鏄€滅簿纭獥鍙?+ 绮剧‘鎵ц鏂瑰紡鈥濓紝涓嶆槸涓€涓ā绯?style銆?
```json
{
  "transition_id": "tx_uuid",
  "from_track_id": "a",
  "to_track_id": "b",
  "from_at_sec": 178.4,
  "to_at_sec": 16.0,
  "fade_sec": 12.0,
  "from_phrase_id": "a_phrase_17",
  "to_phrase_id": "b_phrase_02",
  "phase_anchor_sec": 178.4,
  "from_beat_interval_sec": 0.586,
  "to_beat_interval_sec": 0.594,
  "tempo_ratio": 0.9865,
  "style": "vocal_handoff",
  "fallback_style": "echo_freeze",
  "playback_tier": "stem_aware",
  "automation": {
    "stem_curves": {},
    "eq_curves": {},
    "fx": []
  },
  "scores": {
    "total": 0.86,
    "phrase_alignment": 0.95,
    "beat_compatibility": 0.91,
    "key_compatibility": 0.76,
    "energy_continuity": 0.88,
    "vocal_safety": 0.93,
    "bass_safety": 0.84,
    "loudness_safety": 0.90
  },
  "tags": ["stem_aware", "clean_outro", "clean_intro"],
  "risks": [],
  "confidence": 0.86,
  "evidence_level": "measured"
}
```

绾︽潫锛?
- scorer 蹇呴』瀵硅繖缁?`from_at_sec`銆乣to_at_sec` 鍜?`fade_sec` 鏈韩璇勫垎銆?- executor 蹇呴』鎵ц鍚屼竴缁勬椂闂寸偣銆?- RK 鍙厑璁稿洜鑳藉姏涓嶈冻鍒囨崲鍒?`fallback_style`锛屽苟璁板綍瀹為檯 tier銆?- fallback 涔熻鎻愬墠鐢熸垚锛屼笉鑳藉埌鐜板満涓存椂鎷煎噾銆?
## 5.3 `MixPlanV2`

```json
{
  "schema_version": "mix-plan-v2",
  "plan_id": "plan_uuid",
  "session_id": "session_uuid",
  "template": "cypher_wave",
  "tracks": ["a", "b", "c", "d"],
  "transitions": [
    {
      "selected": {},
      "fallback": {}
    }
  ],
  "fallback_tracks": ["safe_1", "safe_2"],
  "generated_at": "ISO-8601",
  "planner_version": "2026-06-01.1"
}
```

## 5.4 RK `/xfade` 璇锋眰

```json
{
  "transition_id": "tx_uuid",
  "to_song_id": "b",
  "fade_sec": 12.0,
  "to_at_sec": 16.0,
  "style": "vocal_handoff",
  "fallback_style": "echo_freeze",
  "tempo_ratio": 0.9865,
  "stem_curves": {},
  "eq_curves": {},
  "phase_anchor_sec": 178.4
}
```

edge-agent 杩斿洖锛?
```json
{
  "ok": true,
  "transition_id": "tx_uuid",
  "requested_tier": "stem_aware",
  "actual_tier": "stem_aware",
  "actual_style": "vocal_handoff",
  "degraded": false,
  "degrade_reason": null
}
```

---

## 6. 鍒嗘敮涓庡悎骞剁瓥鐣?
## 6.1 鎺ㄨ崘鍋氭硶

涓嶈鐩存帴鍦ㄦ棫涓荤嚎涓婄户缁爢琛ヤ竵銆備娇鐢ㄦ帹鑽愰泦鎴愬垎鏀綔涓烘柊宸ヤ綔璧风偣锛?
```bash
git fetch --all --prune
git switch -c codex/dj-automix-v2 origin/codex/integrate-analysis-session
```

鍘熷洜锛?
- 璇ュ垎鏀凡缁忓寘鍚綋鍓嶄富绾裤€?- 宸茬粡鍚堝叆 DJ Set pipeline銆丄pp 鏂扮晫闈㈠拰 sync-worker 淇銆?- Python 缂栬瘧鍜岀幇鏈夋祴璇曞凡閫氳繃銆?
## 6.2 绂佹鍋氭硶

涓嶈鎵ц锛?
```bash
git merge origin/codex/rk3588-edge-prefetch-and-stem-fixes
```

鐙珛 RK 鍒嗘敮鍩轰簬鍙︿竴濂楀巻鍙诧紝鏁村垎鏀悎骞朵細瑕嗙洊褰撳墠 `cypher-integration/rk3588-edge/` 涓凡缁忓瓨鍦ㄧ殑娴嬭瘯銆乣playback_tier`銆乫allback 鍜?vocal handoff 淇銆?
姝ｇ‘鍋氭硶鏄細闃呰鐙珛 RK 鍒嗘敮瀵瑰簲鏂囦欢锛屾墜鍔ㄧЩ妞嶉渶瑕佺殑瀛楁銆佹帴鍙ｅ拰闊抽鏂规硶銆?
## 6.3 鏈湴鏈彁浜ゆ敼鍔?
褰撳墠鐢ㄦ埛宸ヤ綔鍖哄瓨鍦ㄦ湭鎻愪氦鏀瑰姩銆備笉寰楀洖婊氭垨瑕嗙洊锛?
- `app/modules/session/coordinator.py`
- `app/modules/session/scene_playlist.py`
- iOS 閰嶇疆銆佽剼鏈拰宸叉湁鏂囨。

濡傛灉鍚屼簨鍦ㄦ柊 clone 涓墽琛岋紝涓嶉渶瑕佸鐞嗚繖浜涙湰鍦版枃浠躲€傚鏋滃湪鐢ㄦ埛褰撳墠鏈哄櫒鎵ц锛屽厛鍒涘缓澶囦唤鍒嗘敮鎴?patch锛屽啀寮€濮嬮泦鎴愩€?
---

## 7. 鍙墽琛屽疄鏂借鍒?
姣忎釜 Phase 鍗曠嫭鎻愪氦銆備笉寰楁妸鎵€鏈夋敼鍔ㄥ杩涗竴涓?commit銆?
## Phase 0锛氬缓绔嬪畨鍏ㄥ伐浣滃垎鏀苟娓呯悊鍑嵁

鐩爣锛氳幏寰楀彲宸ヤ綔鐨勯泦鎴愬熀绾匡紝涓嶆惡甯︽槑鏂囧瘑鐮併€?
### 淇敼

1. 浠?`origin/codex/integrate-analysis-session` 鍒涘缓 `codex/dj-automix-v2`銆?2. 淇敼 `scripts/auto_mix_e2e.py`锛?   - 鍒犻櫎纭紪鐮佷簯绔?IP銆丷K IP銆佽处鍙峰拰瀵嗙爜銆?   - 鏀逛负鐜鍙橀噺鎴?CLI 鍙傛暟銆?   - 瀵嗙爜鍙厑璁告潵鑷幆澧冨彉閲忥紝涓嶆墦鍗般€?3. 濡傛灉鑴氭湰涓殑瀵嗙爜鏇剧湡瀹炰娇鐢紝杞崲璇ュ嚟鎹€?
### 鎺ㄨ崘鐜鍙橀噺

```bash
HARBEAT_GATEWAY_URL=
HARBEAT_RK_URL=
HARBEAT_USERNAME=
HARBEAT_PASSWORD=
HARBEAT_RK_TOKEN=
```

### 楠屾敹

```bash
git grep -nE 'PWD\\s*=|PASSWORD\\s*=|temppwd|12345678'
```

涓嶅簲鍑虹幇鎻愪氦鍒颁粨搴撶殑鐪熷疄瀵嗙爜銆?
### 鎻愪氦寤鸿

```bash
git add scripts/auto_mix_e2e.py
git commit -m "fix(security): remove tracked automix e2e credentials"
```

## Phase 1锛氬缓绔嬪敮涓€ `TransitionCandidate` 鍜?`MixPlanV2`

鐩爣锛歋et planner 璇勫垎銆丄pp 灞曠ず鍜?RK 鎵ц浣跨敤鍚屼竴浠借鍒掋€?
### 淇敼鏂囦欢

| 鏂囦欢 | 浠诲姟 |
|------|------|
| `app/modules/dj_set/edge_analyzer.py` | 杈撳嚭澶氫釜绮剧‘ window candidate锛涙瘡涓?candidate 鍖呭惈 `from_at_sec`銆乣to_at_sec`銆乣fade_sec` |
| `app/modules/dj_set/transition_plan.py` | 鎺ユ敹宸茬粡閫夊畾鐨勭簿纭獥鍙ｏ紱绂佹閲嶆柊涓㈠け `entry_time` |
| `app/modules/dj_control/mixer_rules.py` | 鏂板鈥滀娇鐢ㄦ寚瀹氱獥鍙ｇ敓鎴?spec鈥濈殑鍏ュ彛锛涙棫鑷姩閫夌偣淇濈暀涓?fallback |
| `app/modules/dj_set/service.py` | 杈撳嚭 `MixPlanV2`锛屾瘡娈靛寘鍚?selected 鍜?fallback |
| `mobile/lib/src/dj_control_page.dart` | `_applySetToSequence()` 鍚屾椂淇濆瓨 `plans[]`锛涚幇鍦哄垏姝屼紭鍏堟秷璐归€変腑 Set 鐨勮鍒?|
| `mobile/lib/src/edge_agent_client.dart` | `/xfade` 澧炲姞 `transition_id`銆乣fallback_style`銆乣eq_curves`銆乣phase_anchor_sec` |

### 鍏抽敭瑙勫垯

- App 閫変腑涓€涓?Set 鍚庯紝蹇呴』淇濆瓨璇?Set 鐨?`plans[]`銆?- 鎾斁绗?`n -> n+1` 棣栨椂锛孉pp 鐩存帴鍙栧悓涓€绱㈠紩鐨?transition銆?- 鍙湁璁″垝缂哄け鎴栧凡澶辨晥鏃讹紝鎵嶈皟鐢ㄦ棫 `/api/dj/transitions/plan` fallback銆?- fallback 鍙戠敓鏃讹紝璁板綍浜嬩欢鍜屽師鍥犮€?
### 蹇呴』澧炲姞鐨勬祴璇?
1. `edge_analyzer` 璇勫垎鍏ュ彛绛変簬璁″垝鍏ュ彛銆?2. App 閫変腑 Set 鍚庝笉浼氫涪寮?`plans[]`銆?3. 璁″垝涓殑 `transition_id` 浼氫紶鍒?RK銆?4. 鏃?payload 浠嶅彲宸ヤ綔銆?
### 楠屾敹

鐑熼浘鑴氭湰蹇呴』鎵撳嵃骞舵柇瑷€锛?
```text
edge.entry_time == plan.spec.to_at_sec
edge.exit_time  == plan.spec.from_at_sec
```

### 鎻愪氦寤鸿

```bash
git commit -m "feat(automix): make transition candidates canonical end to end"
```

## Phase 2锛氳 Set planner 浣跨敤鐪熷疄 C1 鍒嗘瀽

鐩爣锛氫笉鍐嶇敤宸叉湁浜嬪疄鐨勪綆璐ㄩ噺鏇夸唬鐗┿€?
### 鏂板缓鏂囦欢

`app/modules/dj_set/track_analysis_adapter.py`

鑱岃矗锛?
- 鎶?`LibrarySong` 杞负 `TrackAnalysisV2`銆?- 浼樺厛璇诲彇 C1 鐨勭湡瀹炲瓧娈点€?- 瀛楁缂哄け鏃跺厑璁?proxy fallback锛屼絾鏍囪 `evidence_level=proxy`銆?- 鎶?`needs_review` 浼犳挱缁?candidate scorer銆?
### 淇敼鏂囦欢

| 鏂囦欢 | 浠诲姟 |
|------|------|
| `app/modules/dj_set/track_profiler.py` | 閫氳繃 adapter 璇诲彇鐪熷疄 vocal銆乥ass銆乻tem quality銆乼ransition windows |
| `app/modules/dj_set/section_energy.py` | 浼樺厛浣跨敤 C1 `energy_curve[]` 鍜?phrase intensity |
| `app/modules/dj_set/edge_analyzer.py` | 鎶?vocal overlap銆乥ass overlap銆丩UFS delta銆乥eat confidence 绾冲叆姣忎釜绮剧‘绐楀彛璇勫垎 |
| `app/modules/dj_set/role_classifier.py` | 鏍℃ `weapon` 闃堝€硷紱浣庤瘉鎹笉寰楄交鏄撳垽楂樿兘瑙掕壊 |
| `app/modules/dj_set/quality_gate.py` | 鍖哄垎鍗遍櫓纭棬妲涘拰鍙欎簨杞儵缃?|

### 寤鸿璇勫垎缁村害

```text
transition_score =
  0.18 phrase_alignment
  0.15 beat_compatibility
  0.10 key_compatibility
  0.13 energy_continuity
  0.14 vocal_safety
  0.14 bass_safety
  0.08 loudness_safety
  0.05 stem_quality
  0.03 cache_readiness
```

瀹夊叏闂細

- `confidence < 0.25`锛氬彧鍏佽瀹夊叏 fallback銆?- stem 涓嶅畬鏁达細绂佹 `stem_aware`銆?- vocal overlap 楂橈細绂佹闀?blend锛屼紭鍏?`vocal_handoff`銆乣echo_freeze` 鎴栫煭 cut銆?- bass overlap 楂橈細绂佹鍙?bass 闀挎椂闂撮噸鍙狅紝浼樺厛 `bass_swap`銆?- BPM 宸窛澶э細绂佹闀?beatmatch锛涗紭鍏?`echo_freeze`銆乣filter`銆乣cut` 鎴?`slam`銆?
### 蹇呴』澧炲姞鐨勬祴璇?
- 鏈夌湡瀹?stems 鏃朵紭鍏堜娇鐢?activity windows銆?- stems 涓嶅畬鏁存椂鑷姩 non-stem銆?- 鍙屼汉澹伴闄╅珮鏃朵笉閫夐暱 blend銆?- 鍙?bass 椋庨櫓楂樻椂涓嶅厑璁告寔缁彔婊°€?- 浣?beatgrid confidence 鏃舵爣璁?`needs_review` 骞堕€夋嫨瀹夊叏鏂规銆?
### 鎻愪氦寤鸿

```bash
git commit -m "feat(automix): score exact seams from measured track analysis"
```

## Phase 3锛氳ˉ榻?RK 鍗忚鍜屽疄鏃?DSP

鐩爣锛氳 RK 鐪熸鎵ц App 宸茬粡涓嬪彂鐨勫弬鏁般€?
### 浠庣嫭绔?RK 鍒嗘敮閫夋嫨鎬хЩ妞?
鍙傝€冨垎鏀細

```text
origin/codex/rk3588-edge-prefetch-and-stem-fixes
```

鍙傝€冩枃浠讹細

- `edge-agent/edge_agent/models.py`
- `edge-agent/main.py`
- `audio-engine/socket_server.py`
- `audio-engine/engine.py`
- `audio-engine/envelopes.py`

绉绘鍒板綋鍓嶇洰褰曪細

- `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`
- `cypher-integration/rk3588-edge/edge-agent/main.py`
- `cypher-integration/rk3588-edge/audio-engine/socket_server.py`
- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- `cypher-integration/rk3588-edge/audio-engine/envelopes.py`

### 闇€瑕佽ˉ榻愮殑鎺ュ彛

| 鎺ュ彛 | 鐢ㄩ€?|
|------|------|
| `/xfade` | 鎺ユ敹 `tempo_ratio`銆乣stem_curves`銆乣eq_curves`銆乣transition_id` |
| `/prewarm_beatmatch` | 鎻愬墠娓叉煋鐩爣姝岀殑鎷夐€熺増鏈?|
| `/beat_reinforce` | 瀵硅妭鎷嶅急鐨勮浆鍦哄彲閫夊彔鍔犺妭鎷嶉噰鏍?|
| `/prefetch` | 鎻愬墠瑙ｇ爜鍚庣画姝屾洸鍜?stems |

### 闊抽瀹夊叏瑕佹眰

涓嶈兘鐓ф惉鐙珛 RK 鍒嗘敮涓殑 bass 纭垏鏇茬嚎銆傞渶瑕佹敼鎴愮煭鏃跺钩婊戜氦鎺ワ細

- bass swap 钀藉湪 bar boundary銆?- 浜ゆ帴绐楀彛寤鸿涓?`0.25 鍒?1 bar`銆?- 浣跨敤 equal-power 鎴栧钩婊?S curve銆?- 涓嶅厑璁稿嚭鐜伴暱鏃堕棿鍙?bass 鍙犳弧銆?- 涓嶅厑璁镐骇鐢熺偣鍑诲０銆?- stem-aware 榛樿浣跨敤鍘熷 stems + cue / beat 瀵归綈銆?- non-stem 鎵嶄娇鐢?beatmatched full-track render銆?
`beat_reinforce` 鏄彲閫夊寮猴紝涓嶆槸鎺╃洊鍧忔帴缂濈殑琛ヤ竵銆傚熀纭€杞満涓嶅姞閲囨牱涔熷繀椤绘垚绔嬨€?
### 蹇呴』澧炲姞鐨勬祴璇?
| 娴嬭瘯 | 鏂█ |
|------|------|
| edge-agent xfade forwarding | `tempo_ratio` 鍜?`stem_curves` 鍒拌揪 socket |
| socket forwarding | audio-engine 鏀跺埌瀹屾暣瀛楁 |
| prewarm endpoint | 鍚堟硶 ratio 鍚姩鍚庡彴娓叉煋锛涜秴鑼冨洿 ratio 瀹夊叏璺宠繃 |
| beat reinforce endpoint | 浠呭湪鍚堟硶绐楀彛鍔犲叆浜嬩欢 |
| envelope test | 鏃?clipping銆佹棤闀块潤闊炽€佹棤鎸佺画鍙?bass |
| playback tier | `stem_aware`銆乣non_stem`銆乣basic` 鐘舵€佺湡瀹炲洖浼?|

### 鎻愪氦寤鸿

```bash
git commit -m "feat(rk): execute canonical tempo and stem automation plans"
```

## Phase 4锛氫慨澶?RK 鍚屾鍜?cache 鏍￠獙

鐩爣锛氱礌鏉愬悓姝ュけ璐ユ椂鍙瘖鏂紝缂撳瓨涓嶈兘璇垽銆?
### 淇敼鏂囦欢

`cypher-integration/rk3588-edge/sync-worker/main.py`

### 宸叉湁浼樼偣

- original 鍜?stems 淇濈暀鏈嶅姟绔牸寮忋€?- 閬垮厤 mp3 瀛楄妭琚敊璇懡鍚嶄负 `.wav`銆?- 鏀寔 curl fallback 鍜屾洿闀胯秴鏃躲€?
### 蹇呴』淇

褰撳墠 `_already_valid()` 鍦?sidecar sha256 涓庢湡鏈涘€间竴鑷存椂绔嬪嵆杩斿洖 `True`锛屾病鏈夊厛鏍稿鏂囦欢澶у皬銆傞檲鏃?sidecar 鍙兘璁╂埅鏂枃浠惰褰撴垚鏈夋晥缂撳瓨銆?
淇椤哄簭锛?
1. 鏂囦欢蹇呴』瀛樺湪銆?2. 濡傛灉鏈?expected size锛屽厛姣斿ぇ灏忋€?3. sidecar 鍙綔涓?hash 璁＄畻缂撳瓨浣跨敤锛泂idecar 鑷冲皯璁板綍 size 鍜?mtime銆?4. 涓嬭浇瀹屾垚鍚庡缁堣绠楃湡瀹?sha256銆?5. 鍘熷瓙鏇挎崲鐩爣鏂囦欢鍜?sidecar銆?
### 蹇呴』澧炲姞鐨勬祴璇?
- stale sidecar + truncated file 蹇呴』閲嶆柊涓嬭浇銆?- sha256 涓嶄竴鑷村繀椤绘姤璇婃柇閿欒銆?- stems 缂哄け涓嶅簲鐮村潖 original 鎾斁銆?- mp3 stem 淇濇寔 `.mp3` 鍚庣紑骞跺彲琚?audio-engine 瀹氫綅銆?
### 鎻愪氦寤鸿

```bash
git commit -m "fix(rk-sync): reject stale cache sidecars and preserve audio formats"
```

## Phase 5锛氭妸 SessionCoordinator 鎺ュ叆鐪熷疄鎾斁閾?
鐩爣锛氱幇鍦烘墍鏈夋剰鍥剧粡杩囧敮涓€璋冨害涓績銆?
### 褰撳墠鍘熷瀷

`app/modules/session/coordinator.py` 宸茬粡鏈夛細

- 鐘舵€佹満
- 闃熷垪
- 瀹夊叏姹?- 鎾ら攢鏍?- `next`
- `energy_up`
- `energy_down`
- `hold`
- `talkover`
- `undo`

鏈湴 `_build_transition_command()` 鍙互鐢熸垚 stem automation锛屼絾 `_handle_track_action()` 浠嶈繑鍥炴棫瀛楃涓?style锛屾病鏈夎皟鐢?helper銆?
### 淇敼

1. Coordinator 鎺ユ敹 `MixPlanV2` 鍜屽綋鍓?`transition_id`銆?2. 姝ｅ父鎾斁浼樺厛娑堣垂 Set 涓鐢熸垚鐨?transition銆?3. 鐢ㄦ埛鎸?`Next` 鎴栬兘閲忔棆閽椂锛孋oordinator 鏍规嵁鎰忓浘閲嶆柊鏌ヨ C3锛屼絾浠嶈緭鍑哄畬鏁?`TransitionCandidate`銆?4. `_handle_track_action()` 璋冪敤缁熶竴 compiler锛屼笉鍐嶈嚜宸辨嫾鎺?`{style, fade_sec}`銆?5. safety pool 涓殑姣忛姝屼篃蹇呴』鏈夐璁＄畻 fallback銆?6. App 鍜屽疄浣撴帶鍒跺櫒閮藉彧鍚?Coordinator 鍙?`ButtonIntent`銆?
### P0 鎺у埗鍣ㄨ竟鐣?
| 鎺т欢 | 鐢ㄦ埛璇箟 | 绯荤粺鍔ㄤ綔 |
|------|----------|----------|
| Next | 褰撳墠姝屼笉鍚堥€?| 鍦ㄤ笅涓€ phrase 浣跨敤鏈€瀹夊叏鍊欓€?|
| Energy 鏃嬮挳 | 鏇寸偢鎴栨洿绋?| 璋冩暣鐩爣鑳介噺锛岄噸鏂版帓鍊欓€?|
| Extend | 褰撳墠 groove 鍐嶅欢闀?| 閲忓寲鍒颁笅涓€涓?bar锛屽欢闀?8 bars |
| Talk | 鎴戣璁茶瘽 | ducking锛岀粨鏉熷悗骞虫粦鎭㈠ |
| Undo | 鎾ら攢鍒氭墠鍔ㄤ綔 | 鎭㈠涓婁竴鍙€嗙姸鎬?|
| Master Volume | 鎬讳綋闊抽噺 | RK master gain |

涓嶈鍦?P0 鎺у埗鍣ㄤ笂鏆撮湶 EQ銆乬ain銆乸itch銆乧rossfader銆乻tem mixer 鎴?FX 鍙傛暟銆?
### 蹇呴』澧炲姞鐨勬祴璇?
- `Next` 杈撳嚭 canonical transition銆?- `Energy Up` 浼氭敼鍙樺€欓€夛紝浣嗕笉浼氱牬鍧忓綋鍓嶆挱鏀俱€?- `Extend` 閲忓寲鍒?bar銆?- `Talk` 閲婃斁鍚庡钩婊戞仮澶嶃€?- `Undo` 鑳芥仮澶嶄笂涓€棣栨垨涓婁竴鐘舵€併€?- 缃戠粶鏂紑鏃?safety pool 鍙户缁伐浣溿€?
### 鎻愪氦寤鸿

```bash
git commit -m "feat(session): route live intents through canonical mix plans"
```

## Phase 6锛氭寔涔呭寲 SessionEvent

鐩爣锛氳绯荤粺鑳藉鐩樼湡瀹炴墽琛岀粨鏋溿€?
### 褰撳墠缂哄彛

`app/modules/sessions/router.py` 鐨?`/rk/{session_id}/events` 鍙墦鍗版棩蹇楀苟杩斿洖 accepted锛屾病鏈夊啓鏁版嵁搴撱€?
### 鏂板鏁版嵁琛?
寤鸿鏂板 `rk_session_events`锛?
| 瀛楁 | 绫诲瀷 | 璇存槑 |
|------|------|------|
| `id` | UUID | 涓婚敭 |
| `batch_id` | string | RK flush 鎵规锛屽箓绛夐敭 |
| `session_id` | string | RK session id |
| `rk_id` | string | 璁惧 |
| `event_type` | string | 浜嬩欢绫诲瀷 |
| `event_value` | JSON | 浜嬩欢鍐呭 |
| `event_ts` | datetime | 璁惧鏃堕棿 |
| `received_at` | datetime | 浜戠鎺ユ敹鏃堕棿 |

### 蹇呴』璁板綍

- `plan_loaded`
- `play_started`
- `transition_requested`
- `transition_started`
- `transition_completed`
- `transition_degraded`
- `actual_playback_tier`
- `prefetch_failed`
- `sync_failed`
- `key_press`
- `intent`
- `skip`
- `undo`
- `xrun`

### RK 鏈湴 spool

RK 澶辫触钀界洏涓嶈兘瑕嗙洊鏃т簨浠躲€備娇鐢?append 鎴栧師瀛愰槦鍒楁枃浠讹細

1. 鏂颁簨浠跺啓鍏ヤ复鏃舵枃浠躲€?2. `fsync`銆?3. 鍘熷瓙 rename銆?4. 浜戠纭 batch 鍚庡垹闄ゃ€?5. 閲嶅惎鏃舵仮澶嶆墍鏈夋湭纭 batch銆?
### 蹇呴』澧炲姞鐨勬祴璇?
- 鍚屼竴 `batch_id` 閲嶅彂涓嶄細閲嶅鍐欏簱銆?- 浜戠澶辫触鍚?RK 涓嶄涪浜嬩欢銆?- RK 閲嶅惎鍚庢仮澶?spool銆?- App 鍙互鏌ヨ鏌愭 transition 鐨勫疄闄?tier 鍜岄檷绾у師鍥犮€?
### 鎻愪氦寤鸿

```bash
git commit -m "feat(events): persist idempotent rk session event batches"
```

## Phase 7锛氱绾块煶璐ㄨ瘎娴嬨€丷K 璇曞惉鍜岄儴缃?
鐩爣锛氫笉鏄€滄帴鍙ｉ€氫簡鈥濓紝鑰屾槸鍥涢姝岃繛缁挱鏀惧惉璧锋潵鍚堢悊銆?
### 7.1 绂荤嚎璇勬祴

瀵?6 鍒?10 棣栨巿鏉冩瓕鏇茬敓鎴?all-pairs matrix銆傛渶缁?Set 涓瘡涓€涓浉閭?pair 鑷冲皯娓叉煋锛?
- baseline 鏅€?fade
- 鏈€浣?stem-aware 鏂规
- 鏈€浣?non-stem fallback

姣忎唤鎶ュ憡杈撳嚭锛?
| 鎸囨爣 | 鐢ㄩ€?|
|------|------|
| peak dBFS | 妫€鏌?clipping |
| integrated LUFS / 鍒嗘 loudness | 妫€鏌ラ煶閲忚烦鍙?|
| silence duration | 妫€鏌ユ柇闊?|
| low-band overlap | 妫€鏌ュ弻 bass |
| vocal overlap | 妫€鏌ュ弻浜哄０ |
| transient click score | 妫€鏌ョ偣鍑诲０ |
| energy before / during / after | 妫€鏌ヨ浆鍦烘槸鍚︽垱鐒惰€屾 |
| actual tier | 妫€鏌ユ槸鍚︽寜璁″垝璧?stems |

### 7.2 鏈湴娴嬭瘯鍛戒护

```bash
python3 -m py_compile \
  app/modules/dj_set/*.py \
  app/modules/dj_control/*.py \
  app/modules/session/*.py \
  cypher-integration/rk3588-edge/audio-engine/*.py \
  cypher-integration/rk3588-edge/edge-agent/*.py \
  cypher-integration/rk3588-edge/edge-agent/edge_agent/*.py \
  cypher-integration/rk3588-edge/sync-worker/main.py

python3 -m pytest app/tests -q
python3 -m pytest cypher-integration/rk3588-edge/tests -q
python3 scripts/dj_set_smoke.py

cd mobile
flutter analyze
```

褰撳墠瀹¤鍩虹嚎锛?
- 鍚庣娴嬭瘯锛歚143 passed`
- RK 闆嗘垚娴嬭瘯锛歚19 passed`
- Python 缂栬瘧锛氶€氳繃
- Flutter analyze锛氬彲浠ュ畬鎴愶紝浣嗘湁 41 涓?lint / deprecated 鎻愮ず銆傚畠浠笉鏄綋鍓嶉煶棰戦摼闃绘柇椤癸紝鍚庣画鍗曠嫭娓呯悊銆?
### 7.3 RK 鍦ㄧ嚎鍚庣殑鐪熸満楠屾敹

鍏堣缃細

```bash
export RK_IP=192.168.5.100  # 璁惧鍦ㄧ嚎鍚庢浛鎹负褰撴椂妫€娴嬪埌鐨?RK IP
export RK_HOST="cat@$RK_IP"
export RK_URL="http://$RK_IP:8765"
```

閮ㄧ讲鍓嶅浠斤細

```bash
ssh "$RK_HOST" 'ts=$(date +%Y%m%d-%H%M%S); cp -a /home/cat/cypher "/home/cat/cypher.bak.$ts"'
```

閮ㄧ讲鏃跺彧瑕嗙洊鏈疆纭鏂囦欢锛屼笉涓婁紶 `.env`銆丣WT銆佽澶囧瘑鐮佹垨 token銆?
閲嶅惎锛?
```bash
ssh "$RK_HOST" 'sudo systemctl restart cypher.target'
```

鍋ュ悍妫€鏌ワ細

```bash
curl "$RK_URL/health"
curl "$RK_URL/state"
```

鐪熸満鎾斁楠屾敹锛?
1. `/load_plan` 鍚屾鍥涢姝?original + stems銆?2. `/play` 鎾斁绗竴棣栥€?3. 杩炵画鎵ц涓夋 `/xfade`銆?4. 鑷冲皯鏈変竴娈?`stem_aware`銆?5. 鑷冲皯鏈変竴娈靛己鍒?`non_stem` fallback銆?6. 姣忔閮芥鏌?`actual_tier`銆佷簨浠舵棩蹇楀拰涓昏鍚劅銆?7. 妫€鏌?7 / 8 / 9 stem FX 鎴栭殣钘忓伐绋嬪叆鍙ｏ紝涓嶆妸瀹冧滑鏆撮湶涓?P0 鐢ㄦ埛涓绘搷浣溿€?
鍥炴粴锛?
```bash
ssh "$RK_HOST" 'sudo systemctl stop cypher.target; ls -dt /home/cat/cypher.bak.* | head -1'
```

纭澶囦唤鐩綍鍚庡啀鎵ц鎭㈠锛岄伩鍏嶈閫夋棫鐗堟湰銆?
---

## 8. 鍚勭淇敼娓呭崟

## 8.1 Jetson / 浜戠

| 鏂囦欢鎴栨ā鍧?| 淇敼 |
|------------|------|
| `app/modules/library/analysis.py` | 淇濇寔褰撳墠 C1 涓轰簨瀹炴簮锛涜ˉ analysis version 鍜?evidence level |
| `app/modules/library/stem_analysis.py` | 鏍″噯 stem quality锛屼繚鐣?activity windows |
| `app/modules/library/background_tasks.py` | 缁熶竴鍒嗘瀽鐘舵€佹満銆佸け璐ラ噸璇曞拰閲嶇畻 |
| `app/modules/manifest/` | 杈撳嚭 original + 鍥?stems 鐨?url銆乻ize銆乻ha256銆乫ormat |
| `app/modules/dj_set/` | 鎺?TrackAnalysisV2 adapter銆佺簿纭獥鍙?scorer銆丮ixPlanV2 |
| `app/modules/sessions/` | 鎸佷箙鍖?RK events |

## 8.2 Flutter App

| 鏂囦欢 | 淇敼 |
|------|------|
| `mobile/lib/src/dj_control_page.dart` | Set 閫変腑鍚庝繚瀛?plans锛涙挱鏀炬椂娑堣垂 canonical transition |
| `mobile/lib/src/edge_agent_client.dart` | 琛ュ叏 xfade payload锛涙毚闇插疄闄?tier 鍜岄檷绾у師鍥?|
| Live Deck 椤甸潰 | 鍙睍绀虹敤鎴锋剰鍥惧拰涓嬩竴娈佃В閲婏紱楂樼骇 DSP 鏀惧伐绋嬫ā寮?|

## 8.3 RK edge-agent

| 鏂囦欢 | 淇敼 |
|------|------|
| `edge-agent/edge_agent/models.py` | 鎵╁睍 `XfadeRequest`锛涙柊澧?prewarm 鍜?reinforce model |
| `edge-agent/main.py` | 鏂板 endpoint锛涘畬鏁磋浆鍙戯紱璁板綍瀹為檯 tier |
| `edge-agent/edge_agent/state.py` | 鏀逛簨浠?spool 涓哄箓绛夊師瀛愰槦鍒?|

## 8.4 RK audio-engine

| 鏂囦欢 | 淇敼 |
|------|------|
| `audio-engine/socket_server.py` | 杞彂瀹屾暣 xfade銆乸rewarm銆乺einforce |
| `audio-engine/engine.py` | 鎵ц tempo ratio銆乻tem curves銆乫allback銆乸refetch |
| `audio-engine/envelopes.py` | 骞虫粦 bass swap 鍜?vocal handoff |
| `audio-engine/transition_planner.py` | 鍙仛 RK 鑳藉姏鏍￠獙鍜岄檷绾э紝涓嶅彟璧蜂竴濂?DJ 鍐崇瓥 |

---

## 9. 涓嶅簲缁х画鍋氱殑浜嬫儏

1. 涓嶈缁х画澧炲姞鏂?preset锛岀洿鍒?canonical transition 鐪熸璐€氥€?2. 涓嶈鏁村垎鏀悎骞剁嫭绔?RK 瀹為獙鍒嗘敮銆?3. 涓嶈璁?App 鍦ㄦ墽琛屽墠閲嶆柊璁＄畻鍙︿竴浠芥帴姝屾柟妗堛€?4. 涓嶈璁?RK 閲嶆柊閫夋嫨鏂扮殑娣峰叆鐐广€俁K 鍙仛瀹夊叏鏍￠獙鍜岄檷绾с€?5. 涓嶈鐢?FX銆侀噰鏍锋垨 beat reinforce 鎺╃洊鍩虹鎺ョ紳闂銆?6. 涓嶈鎶?EQ銆乬ain銆乸itch銆乻tem mixer 鍜?FX 鍙傛暟鏀惧埌 P0 鎺у埗鍣ㄨ〃闈€?7. 涓嶈鎶婂瘑鐮併€丣WT銆丷K token 鎴栬澶?`.env` 鎻愪氦鍒?Git銆?8. 涓嶈涓嬭浇鏈巿鏉冮煶涔愩€傛祴璇曟洸搴撲娇鐢ㄥ凡鏈夋巿鏉冩洸鐩€?
---

## 10. Definition of Done

鍙湁婊¤冻浠ヤ笅鏉′欢锛屾墠绠楃涓€鐗?DJ Automix 鍏ㄩ摼璺畬鎴愶細

### 10.1 璁″垝涓€鑷存€?
- Set planner銆丄pp銆丷K 浣跨敤鍚屼竴涓?`transition_id`銆?- scorer 璇勫垎鐨?`from_at_sec` 鍜?`to_at_sec` 涓?audio-engine 鎵ц鍊间竴鑷淬€?- 姣忔閮芥彁鍓嶇敓鎴?fallback銆?
### 10.2 闊抽

- 鍥涢姝岃繛缁挱鏀炬椂娌℃湁鎴涚劧鑰屾銆?- 娌℃湁 clipping銆?- 娌℃湁闀块潤闊炽€?- 娌℃湁鎸佺画鍙?bass 鍙犳弧銆?- 鍙屼汉澹伴珮椋庨櫓 pair 鑷姩瑙勯伩鎴栭檷绾с€?- stem-aware 鍜?non-stem 閮藉彲鐙珛宸ヤ綔銆?
### 10.3 鍙潬鎬?
- RK 缂撳瓨鎹熷潖鑳借璇嗗埆骞堕噸涓嬨€?- Jetson銆佷簯绔垨 App 鏆傛椂鏂紑鏃讹紝RK 浣跨敤缂撳瓨缁х画鎾斁銆?- 浜嬩欢鍙仮澶嶃€佸彲鏌ヨ銆佷笉浼氶噸澶嶅啓鍏ャ€?- `playback_tier` 鍜岄檷绾у師鍥犲 App 鍙銆?
### 10.4 浜у搧杈圭晫

- 鏅€氱敤鎴峰彧闇€瑕佹帶鍒舵剰鍥俱€?- 楂樼骇 DSP 鐣欏湪绠楁硶鍜屽伐绋嬫ā寮忋€?- P0 瀹炰綋鎺у埗鍣ㄥ彧瀹炵幇鍏釜鏍稿績鎺т欢銆?
---

## 11. 寤鸿鎵ц椤哄簭鎽樿

鍚屼簨鎷垮埌鏂囨。鍚庯紝鎸変互涓嬮『搴忓伐浣滐細

1. 浠?`origin/codex/integrate-analysis-session` 鍒涘缓鏂板垎鏀€?2. 娓呯悊 E2E 鑴氭湰涓殑鏄庢枃鍑嵁銆?3. 寤虹珛 `TrackAnalysisV2`銆乣TransitionCandidate` 鍜?`MixPlanV2`銆?4. 淇 Set 璁″垝鍦?App 涓涓㈠純鐨勯棶棰樸€?5. 淇 scorer 鍜?executor 浣跨敤涓嶅悓绐楀彛鐨勯棶棰樸€?6. 璁?DJ Set profile 浣跨敤鐪熷疄 C1 鍒嗘瀽锛屼笉鍐嶄緷璧?proxy銆?7. 浠庣嫭绔?RK 鍒嗘敮閫夋嫨鎬хЩ妞?tempo銆乻tem curves銆乸rewarm 鍜?beat reinforce銆?8. 骞虫粦 bass handoff锛岃ˉ榻愬崗璁祴璇曞拰 envelope 娴嬭瘯銆?9. 淇 sync sidecar 鏍￠獙銆?10. 鎺ュ叆 SessionCoordinator銆?11. 鎸佷箙鍖?RK SessionEvent銆?12. 鏈湴绂荤嚎娓叉煋鍚庯紝绛夊緟 RK 鍦ㄧ嚎杩涜鍥涢杩炵画璇曞惉鍜岄儴缃层€?
---

## 12. 浜ゆ帴缁?AI Agent 鐨勫紑鍦烘寚浠?
鍙皢涓嬮潰杩欐鐩存帴鍙戦€佺粰鍚庣画 AI锛?
```text
璇蜂弗鏍兼寜鐓?docs/DJ_AUTOMIX_INTEGRATION_EXECUTION_SPEC.md 鎵ц銆?
鍏堥槄璇?docs/DEVELOPMENT_SPEC.md銆乨ocs/MERGE_PLAN.md 鍜屾墽琛岃鏍笺€?浠?origin/codex/integrate-analysis-session 鍒涘缓鏂扮殑 codex/dj-automix-v2 鍒嗘敮銆?涓嶈鏁村垎鏀悎骞?origin/codex/rk3588-edge-prefetch-and-stem-fixes锛屽彧閫夋嫨鎬хЩ妞嶃€?涓嶈鍥炴粴鐢ㄦ埛鏈湴鏈彁浜ゆ敼鍔ㄣ€?姣忎釜 Phase 鍗曠嫭鎻愪氦锛屽厛瀹屾垚鏈湴娴嬭瘯锛汻K 褰撳墠涓嶅湪绾匡紝鐪熸満閮ㄧ讲姝ラ淇濈暀鍒拌澶囧湪绾垮悗鎵ц銆?浠讳綍鍑嵁銆丣WT銆丷K token銆佽澶囧瘑鐮佸拰 .env 绂佹鎻愪氦鍒?Git銆?
绗竴浼樺厛绾т笉鏄柊澧?preset锛岃€屾槸璁?scorer銆丄pp 鍜?RK 鎵ц鍚屼竴浠?canonical TransitionCandidate銆?```
