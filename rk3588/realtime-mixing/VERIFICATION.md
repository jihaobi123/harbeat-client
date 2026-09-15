# 交付验证记录

## 本次整理与上传检查（2026-09-15）

在独立仓库 checkout 中测试，不操作正在播放的 RK，不重启服务。本次运行代码按部署源文件复制；仅修正 test_deployment.py 中 Mac `/var` 与 `/private/var` 符号链接造成的路径比较，未改变生产路径解析逻辑。

在本目录运行：

```bash
python3.11 -m unittest test_deployment test_realtime test_control_api test_tempo test_tempo_control
```

53 项通过：46 项控制/HTTP 字段与去重/候选点/时间映射测试，加 7 项交付数据导入安全测试。不打开声卡，不调用实际播放接口。

转存到 harbeat-client 后重新运行上述 53 项测试，并检查新增目录 Python 语法、JSON、文档内部链接及提交范围。没有运行整个 harbeat-client 后端测试，也没有运行 Ring/Wrist 固件构建；本次不修改这些模块。提交不包含音乐或密钥。

来源说明：该交付最初整理在 harbeat-wear 本地分支（提交 704db52），因当前 SSH 账号无该仓库写入权限，按用户要求改发 harbeat-client。整理时曾在 harbeat-wear 运行原 BLE/Engine IPC 合同校验及 48 项仓库/host 测试，均通过；这些是**设备仓库的历史检查**，不能当作 harbeat-client 的整仓 CI 结果。该设备仓库原有两个文档死链接也未在本次修改。运行代码保持不变，只调整文档仓库路径与来源说明。

## 此前 RK 已完成验证（2026-09-14，本次不重复发声）

| 报告 | 记录内容 |
| --- | --- |
| [控制及缓存单测](verification/tempo_unit_tests.txt) | 46 项控制相关测试、12 项 RK 缓存测试通过；原日志仅改为 txt 扩展名以便纳入 Git |
| [实际引擎 HTTP 模拟第一轮](verification/realtime_tempo_http_test-1789393858.json) | 62 项检查、7 次交接，XRUN 增量 0 |
| [实际引擎 HTTP 模拟第二轮](verification/realtime_tempo_http_test-1789394285.json) | 62 项检查、7 次交接，含最终曲目版本，XRUN 增量 0 |
| [PCM 对比](verification/tempo_pcm_comparison.json) | 7 对相同片段/时刻的原 FFmpeg tri 与 RK callback 对比通过，最大误差 0.0000319481 |
| [末曲结束](verification/tempo_end_test.json) | 末尾 seek 验证到达结束，XRUN 增量 0 |

上述“0”指对应测试时间段内的增量，不是设备从开机至今从未欠载。两轮 HTTP 测试使用诊断 seek 缩短等待，不是整场连续试听。PCM 对比不等于扬声器听感或整场逐字节一致。

没有把软件模拟当作真实 BLE/IMU 验收。真实戒指/手环准确率、重连、误触发和现场整场播放仍需负责人验收。报告中的 track_id、资产哈希和 RK 内部文件路径只是结果溯源，不是下载地址或访问凭据。

## 源码一致性

交付的 engine-patch/engine.py SHA256：

```text
5aa430a104bab79a4b14499740106514e90838e8596e23f847916309f4abfd21
```

与 2026-09-14 验收记录一致。Git 不含音乐、音效素材、环境文件、SSH key、部署备份及原始算法压缩包。依赖与复现条件见 [README](README.md)，不要把下载本目录理解为得到全部运行资产。
