# R1 基础环境备份与恢复步骤

日期：2026-08-14

## 当前制品

通过门禁的设备恢复包保存在 Git 仓库之外：

```text
D:\work\harbeat-device-backups\20260814\accepted\
```

仓库只保存 SHA256、文件数量和禁入内容扫描结果：

```text
deploy/clean-environment/evidence/r1-recovery-bundles-20260814.json
```

恢复包包含启动文件、udev、内核模块配置、ALSA、实时权限、系统级 systemd 配置、Jetson release 信息和 FFmpeg 二进制。它不包含 NetworkManager 密钥、旧 `cypher-*`/`harbeat-*` 业务 unit、热点自动连接 unit、旧源码、venv、site-packages、render cache、日志或任务状态。完整 unit 名称和状态只保存在只读 inventory JSON 中，不作为恢复输入。

## 恢复原则

1. 先使用设备厂商基础镜像恢复相同硬件型号。
2. 校验内核、JetPack/L4T、Python 和系统包版本。
3. 仅从恢复包提取硬件配置进行逐项比较，不整包覆盖 `/etc` 或 `/boot`。
4. RK 的 Rockchip FFmpeg 6.1 必须匹配记录的 SHA256，不能用 Ubuntu 通用 FFmpeg 静默替换。
5. 先在空设备或备用存储介质验证，再允许修改生产设备。
6. 新业务运行时只能从已签名 release 和 wheelhouse 安装，不从恢复包提取旧业务代码。

## 验证顺序

```text
校验恢复包 SHA256
-> 列出归档并检查禁入路径
-> 恢复厂商基础镜像
-> 对比启动和驱动配置
-> 运行 GPU/声卡/网卡/FFmpeg doctor
-> 在临时 root 安装并验证 13 个模块
-> 重启后再次执行 doctor
```

## 门禁状态

当前恢复包已经完成只读生成和完整性验证，但尚未完成整盘镜像与空设备恢复测试。因此：

```text
r1_passed = false
legacy_runtime_quarantine_authorized = false
cleanup_authorized = false
```

不得在此状态下禁用或删除 RK/Jetson 的旧生产服务。
