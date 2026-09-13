# 第一版 Jetson 补丁副本：仅供参考

<!-- harbeat:reference-only -->
第二版业务和控制后续重构；旧补丁只供理解历史问题，不是新实现要求。
**此目录不是当前正式预处理入口。** 它保存旧 DJ 控制、能量策略、轨道特征和后台任务补丁，预计不直接用于第二版后端。

- `app/`：历史补丁/实现副本，不是可直接覆盖线上 app 的发行包。
- `scripts/`：历史补分析脚本，可能写数据库，不作为开工命令。

正式预处理维护在 [preprocessing](../preprocessing/README.md)，部署包装在 [deploy/jetson](../deploy/jetson/README.md)。不要因目录叫 jetson 就用这里替换当前算法。

本轮没有执行补丁或改动设备。边界见 [参考代码说明](../docs/repository/reference-code.md)。
