# Section Labeler 阿里云部署

本目录保存双人段落标注页面的阿里云 ECS 部署配置。访问密钥、音频和标注结果都不进入 Git。

## 运行结构

```text
浏览器
  -> HTTPS /section-labeler/（Nginx + Let's Encrypt IP 证书）
  -> 127.0.0.1:8765（section_label_workbench.py）
  -> /srv/harbeat-section-labeler/data/annotations.json
  -> /srv/harbeat-section-labeler/audio-root/
```

- Nginx 只把 `/section-labeler/` 子路径转发给标注服务，不改变现有 `/` 网关。
- 标注服务只监听回环地址，由 systemd 自动启动和故障重启。
- `prepare_dataset.py` 复制数据集并把本机绝对音频路径改写为服务器路径；它不改变歌曲、段落、分区或人工标签。
- 页面通过同一个子路径请求数据、提交结果和读取音频，支持音频 Range 请求。
- 证书续期任务每天运行三次。IP 证书有效期较短，因此不能停用该定时器。

## 服务器路径

| 内容 | 路径 |
| --- | --- |
| 程序 | `/opt/harbeat-section-labeler` |
| 当前标注数据 | `/srv/harbeat-section-labeler/data/annotations.json` |
| 音频根目录 | `/srv/harbeat-section-labeler/audio-root` |
| Nginx 子路径片段 | `/etc/nginx/snippets/harbeat-section-labeler.conf` |
| IP 证书 | `/etc/letsencrypt/live/8.136.120.255/` |

## 上线检查

```bash
systemctl is-active nginx harbeat-section-labeler harbeat-dns
systemctl is-enabled harbeat-certbot-renew.timer
systemctl list-timers harbeat-certbot-renew.timer
curl -I https://8.136.120.255/section-labeler/
```

上传新数据集时必须先停止标注服务，保存现有结果备份，再运行 `prepare_dataset.py`，避免覆盖标注者正在提交的数据。正式入口应使用固定 ECS HTTPS 地址，不使用临时 Cloudflare Tunnel 或开发者电脑地址。

分类器的数据合同、训练结构和评审口径见 `docs/songformer_section_relabeler_architecture.md` 与 `docs/songformer_section_relabeler_training.md`。
