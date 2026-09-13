# 部署文件：先区分用途

本目录混有正式预处理包装与历史整套服务部署，不能整体执行。

| 位置 | 用途 | 当前定位 |
|---|---|---|
| [jetson](jetson/README.md) | 正式预处理、曲库导入、人声补分析包装与服务单元 | 继续维护；整理后的源码尚未切换到线上 |
| `cloud_gateway/app/` | 既有公网网关代码 | 阿里云入口职责保留；第二版鉴权/资源传输须重新设计核对，不能认定现成可用 |
| `JETSON_SETUP.md`、`setup-server.sh`、`nginx.conf`、`daemon.json`、`.env.example` | 旧整套业务服务安装及配置 | 第一版参考；不能按旧说明覆盖当前服务器 |
| 根目录 Dockerfile、docker-compose、start/stop/deploy 脚本 | 历史服务构建启动 | 第一版参考，不是第二版一键部署方案 |

正式位置及上次线上核对记录见 [部署位置](../docs/repository/deployment-map.md)。旧业务、手机、RK 后续重构，预计不直接使用，见 [参考边界](../docs/repository/reference-code.md)。

本轮没有运行部署脚本、重启服务、迁移数据库或变更 NAS。
