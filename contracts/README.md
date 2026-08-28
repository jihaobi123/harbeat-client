# HarBeat 共享合同目录

状态：`SCaffold / 尚未冻结`
目标：成为后端、算法、手机和 RK 之间机器可读合同的唯一来源。

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
| 中央 OpenAPI | `docs/backend-handoff-v1/06_手机后端API.openapi.yaml` | draft，后端/手机需评审 |
| Analysis | `docs/backend-handoff-v1/04_音乐分析输入输出合同.md`、`modules/stem-separation/contracts/` | draft/版本漂移，不能冻结 |
| RK | `docs/backend-handoff-v1/08_RK设备能力与控制协议.md` | 设计草案，需形成 Schema |
| Manifest | `docs/backend-handoff-v1/09_资源Manifest与同步协议.md` | 设计草案，需形成 Schema |
| 错误/幂等 | `docs/backend-handoff-v1/10_错误码幂等与离线恢复.md` | 设计草案，需进入消费者测试 |

## 合同文件进入本目录的门槛

1. 明确 owner、reviewer 和语义版本；
2. 禁止 NaN/Infinity 和未定义单位；
3. 明确 null、unknown enum 和兼容策略；
4. 至少具备 success、degraded/null、invalid、timeout/retry 和前一版本 fixture；
5. 生产者与全部消费者合同测试通过；
6. 记录部署顺序、兼容窗口和回滚方法；
7. 合并后更新 `/api/v1/system/build` 或对应 RK build 信息。

在满足这些条件前，文件状态只能是 `draft`，不能用于对外声称接口已冻结。
