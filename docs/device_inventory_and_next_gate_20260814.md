# 设备只读盘点与下一准入门

日期：2026-08-14

## 结论

本轮没有清理、安装、重启或覆盖任何设备服务。当前结果是：

| 设备 | 真实状态 | 下一步 |
|---|---|---|
| RK3588 `192.168.93.209` | `9000/health`、`9000/state`、`9100/status` 均返回 200；Python 3.10 和 ALSA 设备已确认；隔离 venv 12/12 wheel 导入通过 | 进入 adapter 独立 smoke test，不接管旧端口 |
| Jetson `100.87.142.21` | SSH 只读成功；Ubuntu 22.04、Python 3.10、JetPack R36.3、Orin GPU、FFmpeg 已确认；旧 API 本机健康 | 在 `/opt/harbeat-clean` 等新目录做基础环境预检，不接管旧 systemd |

## 重要区分

- RK 的 HTTP 可用只证明旧 edge-agent/sync-worker 正在工作，不证明新模块已部署。
- Jetson 的本机 `127.0.0.1:8000/health` 返回 200；通过 `100.87.142.21:8000` 返回 502，属于访问路径或代理问题，不能当作新环境健康通过。
- Jetson 仍由旧 `harbeat-api.service` 指向 `/home/mark/harbeat` 和旧 venv。该服务仅作为行为参考，不能迁移到新环境。
- RK 正确维护用户为 `cat`。本机必须连接 `0110wow` 的 `192.168.93.x` 网段；切换到其他 WLAN 时，RK 的 SSH 和 HTTP 都会超时。

## 阶段 B 验证结果

| 门禁 | Jetson | RK3588 |
|---|---:|---:|
| `inventory.py` 真实执行 | 通过 | 通过 |
| Python | 3.10.12 | 3.10.12 |
| 架构 | aarch64 | aarch64 |
| wheel SHA256 | 12/12 | 12/12 |
| 隔离 venv wheel 导入 | 12/12 | 12/12 |
| 旧服务修改 | 否 | 否 |

阶段 B 的基础运行时门禁通过。该结论不等于生产 adapter、E2E 或旧环境清理准入通过。

## 已记录文件

- `deploy/clean-environment/inventory-rk.json`
- `deploy/clean-environment/inventory-jetson.json`
- `deploy/clean-environment/acceptance-report-v0.3.0.json`

## 下一步执行顺序

1. 为 Jetson/RK 补齐生产 adapter，每个服务独立启动并使用影子端口 health check。
2. adapter 必须只引用 clean release、独立配置和独立状态目录，不引用旧 venv、旧 systemd 或旧缓存。
3. 各服务 smoke test 通过后，再做新旧链路影子对比。
4. 影子验收通过前，`cleanup_authorized` 必须保持 `false`。

## 清理准入

当前仍为：

```text
production_ready = false
cleanup_authorized = false
```

只有真实模块运行时、手机-Jetson-RK E2E、空设备重建和 rollback drill 全部通过，才允许制作旧盘只读归档并清理旧运行目录。
