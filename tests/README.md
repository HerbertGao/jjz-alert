测试目录结构
================

```
tests/
├── unit/            # 单元测试，按照作用域再细分
│   ├── app/         # 应用入口、调度相关用例
│   ├── core/        # 基础/冒烟级别校验
│   ├── service/     # 业务服务层（JJZ、Traffic、Cache）
│   └── infrastructure/  # 基础设施封装（Redis 等）
├── integration/     # 与外部依赖交互的集成测试
├── performance/     # 性能/压力测试
├── fixtures/        # 可复用的测试数据或辅助脚本
└── tools/           # 测试工具脚本（如 run_tests.py）
```

维护约定
--------
- 新增用例时按照作用域选择对应子目录，保持层次清晰。
- 若需要共享的数据或构造逻辑，请放在 `fixtures/` 或 `conftest.py` 中。
- 运行方式保持不变：`pytest tests/unit/` 依旧能够自动发现所有单元测试。

