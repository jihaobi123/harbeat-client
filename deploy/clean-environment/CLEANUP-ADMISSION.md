# 设备清理准入报告模板

当前结论：

```text
production_ready = false
cleanup_authorized = false
```

本文件是门禁模板，不是清理授权。必须分别保存以下文件并由负责人审核：

- `inventory-rk.json`
- `inventory-jetson.json`
- `assets-manifest.json`
- `database-export-manifest.json`
- `release-acceptance-report.json`
- `rollback-drill-report.json`

## 只读盘点命令

在目标设备上从新的 release 目录运行：

```bash
python3 deploy/clean-environment/inventory.py \
  --root /opt/harbeat/current \
  --output /tmp/harbeat-inventory-$(hostname).json
```

该命令只能采集 OS、内核、Python、systemd unit 列表、监听端口、GPU、声卡、磁盘和 Git 信息，不执行重启、停止、删除、安装或配置修改。

## 只有全部满足才允许清理

- 新基础镜像可以重建。
- 新 release 可以从 GitHub 和 wheelhouse 安装。
- 13 个模块测试通过。
- Jetson 真实 GPU、Demucs、数据库、规划和渲染通过。
- RK 真实声卡、同步、编排、播放和实体输入通过。
- 手机、Jetson、RK E2E 通过。
- 自动接歌、快切、能量、风格各连续 5/5。
- 新环境断开旧代码、旧 venv、旧 systemd 和旧缓存后仍运行。
- activate/rollback 演练通过。
- 旧环境已制作只读镜像并校验 SHA256。

不满足任一项时，必须保持 `cleanup_authorized=false`。
