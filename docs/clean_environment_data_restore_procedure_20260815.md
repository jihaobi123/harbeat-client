# HarBeat 数据恢复步骤

适用制品：`D:\work\harbeat-device-backups\20260814`

## PostgreSQL

1. 安装 PostgreSQL 14 客户端和服务端，不复用旧 Python venv。
2. 创建空数据库和最小权限业务用户。
3. 使用 `postgresql-rhythm-prism/database.dump` 执行：

   ```bash
   pg_restore --exit-on-error --no-owner --no-acl --dbname="$DATABASE_URL" database.dump
   ```

4. 将恢复后的精确逐表行数与 `exact-counts-before.tsv` 比对。
5. 验证 `library_songs=43`，且 43 条记录都有 `dj_structure_v2`、Track1 和 Track2 候选。
6. 数据库连接密钥只写入 `/etc/harbeat/secrets`，不得写入 Git 或恢复报告。

本次已在 Jetson 用户拥有的独立临时 PostgreSQL 14 实例完成 restore，13 张业务表行数一致；临时实例和临时数据库已经删除。

## NAS 资产

1. 只读挂载原 NAS，不移动歌曲、stem 或模型。
2. 使用 `nas-assets/music-files-sha256.json` 和 `nas-assets/models-sha256.json` 校验相对路径、大小、mtime 和 SHA256。
3. 使用 `nas-assets/library-asset-coverage.json` 校验数据库到文件的映射。
4. 当前 43/43 原曲存在，已声明的 168/168 stem 存在；`mt2_o4newg_star_edition` 没有 stem 清单，需要后续重新分轨，但不阻塞原曲 v2 选点和 v7 混音。

## 禁止事项

- 不从 `/home/mark/venvs/harbeat` 复制 site-packages。
- 不把 `/home/mark/harbeat` 当作 clean release 源码。
- 不删除 PostgreSQL、NAS 原文件、Demucs 模型、CUDA 或硬件配置。
- Stage D/E 和 rollback 未通过前，不停止旧服务。
