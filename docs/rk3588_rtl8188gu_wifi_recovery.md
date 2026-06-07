# RK3588 RTL8188GU USB WiFi 修复和复用记录

记录日期：2026-06-04
适用设备：LubanCat RK3588 / Ubuntu 22.04.5 / kernel `6.1.84` / USB WiFi `0bda:b711`

> 安全说明：本文档不写入明文 WiFi 密码、SSH 密码或其他凭据。命令里的 `<WIFI_PASSWORD>`、`<RK_SUDO_PASSWORD>` 请从交接渠道获取，不要提交到 GitHub。

---

## 1. 本次最终结果

RK3588 已经通过 USB WiFi 网卡正常联网：

```text
hostname: lubancat
kernel: 6.1.84 aarch64
USB WiFi: 0bda:b711 Realtek RTL8188GU 802.11n WLAN Adapter
driver module: 8188gu
installed module: /lib/modules/6.1.84/kernel/drivers/net/wireless/rtl8188gu/8188gu.ko
autoload: /etc/modules-load.d/8188gu.conf
interface: wlan0
hotspot SSID: wow0110
RK WiFi IP after connection: 192.168.43.7/24
```

验证结果：

```bash
lsusb | grep -i realtek
lsmod | grep 8188gu
ip -br addr show wlan0
nmcli dev status
curl --interface wlan0 -I --max-time 10 https://github.com
```

本次实测 `wlan0` 能扫描并连接 `wow0110`，并且通过 `wlan0` 单独访问公网返回 `HTTP/2 200`。

---

## 2. 重要限制

这个 `0bda:b711` RTL8188GU 网卡当前只支持 2.4GHz WiFi，不支持 5GHz。

实测信道：

```bash
iwlist wlan0 frequency
```

只显示：

```text
Channel 01-13: 2.412 GHz - 2.472 GHz
```

所以手机热点必须设置为：

```text
2.4GHz
兼容模式
不要只开 5GHz
```

如果热点开成 5GHz，RK 会一直扫不到 SSID。

---

## 3. 现场临时联网方式

如果 RK 还没有 WiFi 驱动，需要先让 RK 临时有网，方便下载源码和安装依赖。

本次使用过的临时方式：

```text
Windows PC 通过网线直连 RK3588
Windows 开启 Internet Connection Sharing
PC Ethernet gateway: 192.168.137.1
RK temporary Ethernet IP: 192.168.137.111
SSH: cat@192.168.137.111
```

RK 侧检查：

```bash
ip -br addr
ip route
cat /etc/resolv.conf
curl -I https://github.com
```

当 `curl -I https://github.com` 返回 `HTTP/2 200` 或类似成功响应后，再开始编译驱动。

---

## 4. 识别 USB WiFi 设备

插入 USB WiFi 后检查：

```bash
lsusb
dmesg | tail -120
ip -br link
nmcli dev status
```

本次设备从 USB mass-storage 模式切换后识别为：

```text
ID 0bda:b711 Realtek Semiconductor Corp. RTL8188GU 802.11n WLAN Adapter (After Modeswitch)
```

如果只看到 `0bda:1a2b`，说明还停留在 Realtek 虚拟光盘 / modeswitch 之前，需要先处理 `usb-modeswitch`。

检查内核自带模块是否支持：

```bash
modinfo rtl8xxxu 2>/dev/null | grep -i b711 || true
modinfo rtl8192cu 2>/dev/null | grep -i b711 || true
```

本次内核自带模块不支持 `0bda:b711`，所以移植外部驱动。

---

## 5. 驱动源码

本次使用的现成驱动仓库：

```text
https://github.com/wandercn/RTL8188GU
```

它明确支持：

```text
VID:PID = 0x0BDA:0xB711
```

RK 上源码目录：

```bash
/home/cat/RTL8188GU-wandercn/8188gu-1.0.1
```

重新准备源码示例：

```bash
cd /home/cat
git clone https://github.com/wandercn/RTL8188GU.git RTL8188GU-wandercn
cd /home/cat/RTL8188GU-wandercn/8188gu-1.0.1
```

---

## 6. 编译环境

确认依赖：

```bash
uname -r
gcc --version
make --version
dpkg -l | grep -E 'build-essential|linux-headers'
ls -ld /usr/src/linux-headers-$(uname -r)
```

本次环境：

```text
Ubuntu 22.04.5 LTS
kernel: 6.1.84
arch: aarch64
headers: /usr/src/linux-headers-6.1.84
```

如缺少依赖：

```bash
sudo apt update
sudo apt install -y build-essential linux-headers-$(uname -r) wireless-tools network-manager
```

---

## 7. kernel headers 修复

### 7.1 恢复 autoconf.h

本次 headers 目录里的 `include/generated/autoconf.h` 丢失，导致外部模块编译失败：

```text
ERROR: Kernel configuration is invalid.
include/generated/autoconf.h or include/config/auto.conf are missing.
```

从 `include/config/auto.conf` 恢复：

```bash
cd /usr/src/linux-headers-$(uname -r)
sudo mkdir -p include/generated

awk '
  /^CONFIG_[A-Za-z0-9_]+=y$/ { split($0,a,"="); print "#define " a[1] " 1"; next }
  /^CONFIG_[A-Za-z0-9_]+=m$/ { split($0,a,"="); print "#define " a[1] "_MODULE 1"; next }
  /^CONFIG_[A-Za-z0-9_]+=$/ { split($0,a,"="); print "#define " a[1] " \"\""; next }
  /^CONFIG_[A-Za-z0-9_]+=/ { split($0,a,"="); v=substr($0,index($0,"=")+1); print "#define " a[1] " " v; next }
' include/config/auto.conf | sudo tee include/generated/autoconf.h >/dev/null

grep -n '^#define CONFIG_BUILD_SALT' include/generated/autoconf.h
```

注意空值配置必须生成空字符串，例如：

```text
#define CONFIG_BUILD_SALT ""
```

如果生成成 `#define CONFIG_BUILD_SALT`，最后编译 `8188gu.mod.o` 会报 `BUILD_SALT` 相关错误。

### 7.2 手动重建 modpost

本次 headers 里的 `scripts/mod/modpost` 缺失或架构不匹配。不要在这个 headers 目录跑完整顶层 `make prepare` 或 `make oldconfig`，因为该 headers 包缺少顶层 `Kconfig`，会把现场弄得更乱。

正确做法是只手动编译 `scripts/mod` 的 host tool：

```bash
cd /usr/src/linux-headers-$(uname -r)

file scripts/mod/modpost scripts/basic/fixdep scripts/kconfig/conf 2>/dev/null || true

sudo rm -f scripts/mod/modpost scripts/mod/modpost.o scripts/mod/file2alias.o scripts/mod/sumversion.o

sudo gcc -Wp,-MMD,scripts/mod/.modpost.o.d \
  -Wall -Wmissing-prototypes -Wstrict-prototypes -O2 -fomit-frame-pointer -std=gnu11 \
  -c -o scripts/mod/modpost.o scripts/mod/modpost.c

sudo gcc -Wp,-MMD,scripts/mod/.file2alias.o.d \
  -Wall -Wmissing-prototypes -Wstrict-prototypes -O2 -fomit-frame-pointer -std=gnu11 \
  -c -o scripts/mod/file2alias.o scripts/mod/file2alias.c

sudo gcc -Wp,-MMD,scripts/mod/.sumversion.o.d \
  -Wall -Wmissing-prototypes -Wstrict-prototypes -O2 -fomit-frame-pointer -std=gnu11 \
  -c -o scripts/mod/sumversion.o scripts/mod/sumversion.c

sudo gcc -o scripts/mod/modpost \
  scripts/mod/modpost.o scripts/mod/file2alias.o scripts/mod/sumversion.o

file scripts/mod/modpost
```

成功时应显示：

```text
ELF 64-bit LSB pie executable, ARM aarch64
```

---

## 8. 驱动源码兼容补丁摘要

如果直接复用 `/home/cat/RTL8188GU-wandercn/8188gu-1.0.1`，这些补丁已经在现场源码里。
如果重新 clone，需要按下面方向重新打补丁。

### 8.1 Makefile 选择 ARM64

确认：

```makefile
CONFIG_PLATFORM_ARM_RPI = n
CONFIG_PLATFORM_ARM64 = y
```

本次为了绕开旧版 cfg80211 API，使用 Wireless Extensions 路径。现象是 `iw dev` 可能为空，但 `iwconfig` 和 `nmcli` 可用，这是正常的。

### 8.2 Linux 6.1 NAPI 签名

`netif_napi_add()` 在新内核中参数变化。修复位置：

```text
os_dep/linux/os_intfs.c
```

逻辑：

```c
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(6, 1, 0))
netif_napi_add(ndev, &adapter->napi, rtw_recv_napi_poll);
#else
netif_napi_add(ndev, &adapter->napi, rtw_recv_napi_poll, RTL_NAPI_WEIGHT);
#endif
```

### 8.3 do_exit 未导出

`do_exit()` 不能被外部模块引用，`MODPOST` 会报：

```text
ERROR: modpost: "do_exit" undefined
```

修复位置：

```text
os_dep/osdep_service.c
```

逻辑：

```c
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(5, 17, 0))
    kthread_complete_and_exit(comp, 0);
#else
    complete_and_exit(comp, 0);
#endif
```

`kthread_complete_and_exit()` 在当前 `6.1.84` headers 中存在：

```bash
grep -RIn 'kthread_complete_and_exit' /usr/src/linux-headers-$(uname -r)/include/linux/kthread.h
```

### 8.4 procfs PDE_DATA 兼容

修复位置：

```text
os_dep/linux/rtw_proc.c
```

逻辑：

```c
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(5, 17, 0))
#define PDE_DATA(inode) pde_data(inode)
#endif
```

### 8.5 随机数 API

旧代码使用 `prandom_u32()`，新内核改为 `get_random_u32()`。

修复位置：

```text
os_dep/osdep_service.c
```

逻辑：

```c
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(5, 17, 0))
return get_random_u32();
#else
return prandom_u32();
#endif
```

### 8.6 netdev dev_addr 警告

旧驱动直接写：

```c
_rtw_memcpy(ndev->dev_addr, mac, ETH_ALEN);
```

Linux 6.1 会在拉起接口时报：

```text
netdevice: wlan0: Incorrect netdev->dev_addr
WARNING: dev_addr_check
```

修复为：

```c
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(5, 17, 0))
eth_hw_addr_set(ndev, mac);
#else
_rtw_memcpy(ndev->dev_addr, mac, ETH_ALEN);
#endif
```

本次涉及文件：

```text
os_dep/osdep_service.c
os_dep/linux/mlme_linux.c
os_dep/linux/os_intfs.c
os_dep/linux/ioctl_linux.c
```

### 8.7 VFS namespace 导入

模块使用了 VFS 内部符号，需要声明 namespace import。

修复位置：

```text
os_dep/linux/os_intfs.c
```

加入：

```c
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
```

### 8.8 inline 重复符号

链接时如果出现 multicast/broadcast/zero MAC helper 重复定义，把下面函数改成 `static inline`：

```text
include/ieee80211.h

is_multicast_mac_addr
is_broadcast_mac_addr
is_zero_mac_addr
```

---

## 9. 编译和安装驱动

在驱动源码目录：

```bash
cd /home/cat/RTL8188GU-wandercn/8188gu-1.0.1
make clean
make -j4 2>&1 | tee /home/cat/rtl8188gu-build-final.log
ls -lh 8188gu.ko
modinfo ./8188gu.ko | sed -n '1,80p'
```

成功结果应包含：

```text
alias: usb:v0BDApB711...
name: 8188gu
vermagic: 6.1.84 SMP mod_unload modversions aarch64
```

临时加载测试：

```bash
sudo rmmod 8188gu 2>/dev/null || true
sudo insmod ./8188gu.ko
sleep 5
dmesg | tail -120
ip -br link
iwconfig 2>/dev/null || true
nmcli dev status
nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list ifname wlan0 | sed -n '1,20p'
```

安装持久化：

```bash
cd /home/cat/RTL8188GU-wandercn/8188gu-1.0.1

sudo mkdir -p /lib/modules/$(uname -r)/kernel/drivers/net/wireless/rtl8188gu
sudo cp -f ./8188gu.ko /lib/modules/$(uname -r)/kernel/drivers/net/wireless/rtl8188gu/8188gu.ko
sudo depmod -a

printf '%s\n' '8188gu' | sudo tee /etc/modules-load.d/8188gu.conf >/dev/null

sudo modprobe -r 8188gu 2>/dev/null || true
sudo modprobe 8188gu
```

验证安装：

```bash
modinfo 8188gu | sed -n '1,20p'
lsmod | grep 8188gu
ip -br link | grep wlan
```

---

## 10. 配置开机自动连接 wow0110

NetworkManager profile 配置：

```bash
sudo nmcli radio wifi on

sudo nmcli connection add type wifi ifname wlan0 con-name wow0110 ssid wow0110 2>/dev/null || true

sudo nmcli connection modify wow0110 \
  connection.interface-name wlan0 \
  connection.autoconnect yes \
  connection.autoconnect-priority 999 \
  connection.autoconnect-retries -1 \
  802-11-wireless.ssid wow0110 \
  802-11-wireless.mode infrastructure \
  802-11-wireless.hidden yes \
  802-11-wireless.cloned-mac-address permanent \
  802-11-wireless.powersave 2 \
  802-11-wireless-security.key-mgmt wpa-psk \
  802-11-wireless-security.psk '<WIFI_PASSWORD>' \
  ipv4.method auto \
  ipv6.method auto

sudo nmcli connection reload
```

确认：

```bash
nmcli -f connection.id,connection.autoconnect,connection.autoconnect-priority,connection.interface-name,802-11-wireless.ssid,802-11-wireless.hidden,802-11-wireless.powersave,802-11-wireless-security.key-mgmt connection show wow0110
```

手动连接测试：

```bash
nmcli dev wifi rescan ifname wlan0 ssid wow0110
sleep 5
nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list ifname wlan0 | grep -F wow0110
sudo nmcli connection up wow0110 ifname wlan0
ip -br addr show wlan0
curl --interface wlan0 -I --max-time 10 https://github.com
```

如果网线还插着，默认路由可能仍优先走 `eth0`，这是正常的。用 `curl --interface wlan0 ...` 可以验证 WiFi 自身出网。拔掉网线后，系统会走 `wlan0`。

---

## 11. 开机重试服务

NetworkManager 已有自动连接能力。为了处理“RK 先开机、手机热点稍后才打开”的情况，本次额外加了一个 systemd 服务，在启动后重复扫描并尝试连接 `wow0110`。

脚本：

```bash
sudo tee /usr/local/bin/connect-wow0110.sh >/dev/null <<'EOF'
#!/bin/bash
set -u

PROFILE="wow0110"
SSID="wow0110"
IFACE="wlan0"
MAX_TRIES=60
SLEEP_SECONDS=10

log() {
  logger -t wow0110-autoconnect "$*"
  echo "wow0110-autoconnect: $*"
}

wait_for_nm() {
  for _ in $(seq 1 30); do
    if systemctl is-active --quiet NetworkManager; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_for_iface() {
  for _ in $(seq 1 60); do
    if nmcli -t -f DEVICE,TYPE device status | grep -q "^${IFACE}:wifi$"; then
      return 0
    fi
    sleep 2
  done
  return 1
}

is_connected() {
  nmcli -t -f NAME connection show --active | grep -Fxq "$PROFILE"
}

main() {
  if ! wait_for_nm; then
    log "NetworkManager not active"
    exit 1
  fi

  if ! wait_for_iface; then
    log "${IFACE} not ready"
    exit 1
  fi

  nmcli radio wifi on >/dev/null 2>&1 || true
  nmcli dev set "$IFACE" managed yes >/dev/null 2>&1 || true

  for _ in $(seq 1 "$MAX_TRIES"); do
    if is_connected; then
      log "already connected to ${PROFILE}"
      exit 0
    fi

    nmcli dev wifi rescan ifname "$IFACE" ssid "$SSID" >/dev/null 2>&1 || true

    if nmcli connection up "$PROFILE" ifname "$IFACE" >/dev/null 2>&1; then
      log "connected to ${PROFILE}"
      exit 0
    fi

    sleep "$SLEEP_SECONDS"
  done

  log "failed to connect to ${PROFILE} after $((MAX_TRIES * SLEEP_SECONDS)) seconds"
  exit 1
}

main "$@"
EOF

sudo chmod 755 /usr/local/bin/connect-wow0110.sh
```

systemd service：

```bash
sudo tee /etc/systemd/system/connect-wow0110.service >/dev/null <<'EOF'
[Unit]
Description=Auto-connect wow0110 hotspot on boot
Wants=NetworkManager.service
After=NetworkManager.service
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/local/bin/connect-wow0110.sh
Restart=on-failure
RestartSec=15s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable connect-wow0110.service
```

测试服务：

```bash
sudo systemctl restart connect-wow0110.service
systemctl status connect-wow0110.service --no-pager -n 40
journalctl -u connect-wow0110.service --no-pager -n 80
```

如果热点当前可见，服务会连接成功后退出。
如果热点不可见，服务会失败后由 systemd 自动重试。

---

## 12. 常见问题和定位

### 12.1 `wow0110` 扫不到

优先确认手机热点是 2.4GHz：

```bash
iwlist wlan0 frequency
nmcli dev wifi rescan ifname wlan0 ssid wow0110
nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list ifname wlan0 | grep -F wow0110
```

如果 `iwlist wlan0 frequency` 只显示 2.4GHz，而手机热点开了 5GHz，RK 必然扫不到。

### 12.2 `iw dev` 没输出

本次驱动走 Wireless Extensions 兼容路径，`iw dev` 可能为空。改用：

```bash
iwconfig
nmcli dev status
nmcli dev wifi list ifname wlan0
```

### 12.3 `MODPOST do_exit undefined`

说明源码里仍然引用了未导出的 `do_exit()`。检查：

```bash
cd /home/cat/RTL8188GU-wandercn/8188gu-1.0.1
grep -RIn 'do_exit\|complete_and_exit\|kthread_complete_and_exit' .
nm -u 8188gu.o | grep do_exit || true
```

修为 `kthread_complete_and_exit(comp, 0)`。

### 12.4 `BUILD_SALT` 编译错误

检查：

```bash
grep -n '^#define CONFIG_BUILD_SALT' /usr/src/linux-headers-$(uname -r)/include/generated/autoconf.h
```

应为：

```text
#define CONFIG_BUILD_SALT ""
```

不是：

```text
#define CONFIG_BUILD_SALT
```

### 12.5 `Incorrect netdev->dev_addr`

检查 dmesg：

```bash
dmesg | grep -E 'Incorrect netdev->dev_addr|dev_addr_check|WARNING:'
```

如果出现，说明还有直接写 `netdev->dev_addr` 的代码路径，需要替换为 `eth_hw_addr_set()`。

### 12.6 模块没有开机加载

检查：

```bash
cat /etc/modules-load.d/8188gu.conf
systemctl status systemd-modules-load --no-pager
lsmod | grep 8188gu
modprobe 8188gu
```

`/etc/modules-load.d/8188gu.conf` 应包含：

```text
8188gu
```

### 12.7 已连接 WiFi 但默认还走网线

网线插着时，路由优先级可能是：

```text
default via 192.168.137.1 dev eth0 metric 100
default via 192.168.43.1 dev wlan0 metric 600
```

这是正常的。拔掉网线后会使用 `wlan0`。如果要单独验证 WiFi 出网：

```bash
curl --interface wlan0 -I --max-time 10 https://github.com
```

---

## 13. 快速复用清单

重装系统后按这个顺序做：

```text
1. 临时给 RK 联网，最好先用网线/ICS
2. 确认 USB ID 是 0bda:b711
3. 准备 linux headers、gcc、make
4. clone wandercn/RTL8188GU
5. 恢复 autoconf.h，必要时手动重建 modpost
6. 应用 Linux 6.1 兼容补丁
7. make -j4 生成 8188gu.ko
8. insmod 测试 wlan0 和 nmcli 扫描
9. cp 到 /lib/modules，depmod，modules-load 开机加载
10. 配置 NetworkManager 的 wow0110 自动连接 profile
11. 启用 connect-wow0110.service
12. 手机热点确认 2.4GHz，再测试拔网线后的真实联网
```
