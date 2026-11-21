# 安澜涂膜盲板交班台账

白班领班依试验工单为两套涂膜检出方案开具同一块实体盲板的清册。两站分别录入仪器判读，核对错录后冻结交件。站库关停后，夜班中心按质控员指定的两份实收件核算。同一实体槽上的分歧和方向性概率用来安排人工复核，次班按签报号领原报告。

## 运行

使用 Python 3.11 标准库和 SQLite。在项目根目录执行下列命令。控制台物化时提供 `check_project.py`，它运行 `tests` 包中的完整原回归并传播失败退出码。

```sh
python3 -B check_project.py
python3 -B -m examples.shift
```

演示会在临时目录创建两座站库和一座中心库，订正一条错录，按确切冻结发行，关闭站库，反序实收和签报，最后重开中心领取。四槽工单的甲站检出槽 1、2、3，乙站仅检出槽 4。四个分歧槽中至少三个朝向甲的等概率情形有五种，共十六种，报告概率为 `5/16`。

## 一天的交班

| 动作 | 公开函数 | 输入、状态和结果 |
| --- | --- | --- |
| 开板 | `plate.register.register(db, plate_id, slots, protocol)` | 将工单的板号、有序实物槽及站别方案固定为清册。相同定义可重登。 |
| 录入 | `reading.admission.record(db, plate_id, station_id, slot, detected, source)` | 单一确认槽取得当前判读号。仪器出处使用 `InstrumentSource(instrument, reference)`。 |
| 勘误 | `reading.correction.correct(db, observation_id, detected, source)` | 当前号换成新号，历史判读及已冻依据保存。 |
| 冻结 | `reading.freeze.freeze(db, plate_id, station_id)` | 核对整板覆盖，按开板序保存该站快照，返回冻结号。 |
| 发行 | `issue.release.issue(db, freeze_id)` | 指定快照生成 `IssuedOriginal`。其 `payload` 可出站，`issue.pickup.pickup_issue` 可按 `issue_id` 领原件。 |
| 实收 | `receipt.admit.admit(db, payload)` | 离线验收，返回含 `receipt_id` 的原首执。`receipt.ledger.get_received_issue` 可按实收号取实际原件。 |
| 签报 | `review.signing.sign(db, first_receipt_id, second_receipt_id)` | 按固定角色和实物槽核算双件，原子写入 `PairedReport` 与回执。 |
| 复领 | `review.readback.read(db, report_id)` | 重开后按号返回概率、分歧槽、双实收出处和签报回执的原存值。 |

各模块位于 `blindplate` 命名空间下。用 `plate.protocol.build_protocol(a_station, a_scheme, b_station, b_scheme)` 取得固定比较方向。板号、站别、方案、槽号、仪器名和出处使用非空可打印文本，首尾不留空白。一块板有一至八个互异确认槽，顺序来自工单。两站使用不同站别。判读严格使用整数 `0` 或 `1`。库内号码为正的 SQLite 整数，站件号为带板、站和冻结身份的 V1 文本。

站库连接依次调用 `initialize_rosters`、`initialize_readings` 和 `initialize_issue_archive`。中心库连接依次调用 `initialize_receipts`、`initialize_reports`。初始化使用各传入连接，适用于新库和已有 V1 库，须在调用方事务之外执行。公开写入口各自提交一个事务，使用未开启事务的连接。站端 `load_frozen_revision` 可按冻结号检查原判读和仪器出处。站件只交付公共字段。中心原样保存首次收到的字节，并以完整 V1 业务值识别等价重投。历史样本在 `examples/legacy`，三份 SQL 转储可导入空 SQLite 库，两份 JSON 文件为独立的原始站件字节。回归在临时库导入这些数据并继续办理 V1 业务。

仅甲检出数为 a，仅乙检出数为 b。共同检出和共同未检出均不计入分歧。概率为 `sum(comb(a+b, k) for k in range(a, a+b+1)) / 2**(a+b)`，用整数计数与 `Fraction` 约分。无分歧时结果为 1。概率无单位，分歧槽遵循物理清册，比较方向由协议固定。到件顺序、签报入参顺序与后续勘误均不改变已签结果。

非法字段、缺槽、重复当前槽、已被替代的勘误号、坏件、同号异文、同站、异板或清册冲突报 `ValueError`。合法未知的板号、判读号、冻结号、原件号、实收号和报告号报 `KeyError`。签报写失败传播 SQLite 错误。报告和回执同时提交，失败时均无新增，质控员可按原双件重试。
