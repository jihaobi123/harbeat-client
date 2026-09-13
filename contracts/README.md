# HarBeat 共享合同目录

状态：**按合同区分，不能一概视为脚手架或全部已冻结。**
目标：成为后端、算法、手机和 RK 之间机器可读合同的唯一来源。

第二版已发布数据使用 `schemas/analysis/same-style-track-preprocess-v1.schema.json`
（基础 1.2.0）和 `schemas/analysis/vocal-activity-v1.schema.json`（人声 1.0.0），以及曲库索引。
这些已有生产者、数据和测试，不因产品第二版而重命名为 2.0。
鼓组 Pair Score 有实现/schema，但实际阈值校准未完成。
下文旧手机/RK业务合同仍是历史草案，不是现行 NAS 合同，也不是已实现的第二版接口。
旧手机、RK 和业务资源传输后续重构，预计不直接使用旧设计。新 APK 源码核对和新业务协议尚未完成；此前第二版交接整理稿也不代表接口已定稿。见 [参考代码与重构边界](../docs/repository/reference-code.md)。

## 目录责任

```text
contracts/
├── schemas/
│   ├── analysis/   # 算法主维护，后端批准
│   ├── rk/         # RK主维护，后端/手机批准
│   └── manifest/   # 后端+RK共同维护，算法/手机评审
├── fixtures/
│   ├── analysis/   # Worker与算法合同场景
│   ├── mobile-api/ # 中央 OpenAPI Mock 场景
│   └── rk/         # Capability/State/Operation/Event/Sync 场景
└── decisions/      # 影响机器合同的 ADR 和变更索引
```

## 当前迁移来源

| 目标 | 当前来源 | 当前状态 |
|---|---|---|
| 当前预处理 / 人声 | `schemas/analysis/` 与正式 publisher / vocal_activity | 已发布格式继续有效；内部特征 schema 不等于公开协议 |
| 旧中央 OpenAPI | `docs/backend-handoff-v1/06_手机后端API.openapi.yaml` | 第一版参考，第二版后续重构 |
| 旧 Analysis 业务合同 | `docs/backend-handoff-v1/04_音乐分析输入输出合同.md` | 第一版参考；旧 modules/stem-separation/contracts 已移除，不再引用 |
| 旧 RK | `docs/backend-handoff-v1/08_RK设备能力与控制协议.md` | 第一版参考，不要求照旧实现 |
| 旧业务 Manifest | `docs/backend-handoff-v1/09_资源Manifest与同步协议.md` | 第一版参考，勿混同当前 NAS manifest |
| 旧错误/幂等 | `docs/backend-handoff-v1/10_错误码幂等与离线恢复.md` | 第一版参考，第二版须另行确认 |

## 合同文件进入本目录的门槛

1. 明确 owner、reviewer 和语义版本；
2. 禁止 NaN/Infinity 和未定义单位；
3. 明确 null、unknown enum 和兼容策略；
4. 至少具备 success、degraded/null、invalid、timeout/retry 和前一版本 fixture；
5. 生产者与全部消费者合同测试通过；
6. 记录部署顺序、兼容窗口和回滚方法；
7. 提供可追溯的生产者与消费者版本信息；具体第二版接口路径另定，不要求沿用旧 `/api/v1/system/build`。

在满足这些条件前，文件状态只能是 `draft`，不能用于对外声称接口已冻结。
