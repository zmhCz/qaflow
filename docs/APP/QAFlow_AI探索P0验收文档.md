# QAFlow AI 探索 P0 验收文档

> 日期：2026-07-20
> 范围：APP 自动化中心 / AI 探索测试 / 目标巡检
> 目标：验证目标巡检是否达到“稳定、可重复、可诊断”的短期交付标准。

## 1. 验收结论口径

P0 不验收“AI 自主探索能力”，只验收受控目标巡检闭环。

当前 P0 通过标准如下：

| 指标 | 通过标准 | 数据来源 |
| --- | --- | --- |
| 三次执行基线 | 同一任务最近执行不少于 3 次 | `target_consistency.run_count` |
| 目标识别率 | 不低于 85% | `target_consistency.recognition_rate` |
| 锚点恢复成功率 | 不低于 95% | `target_consistency.anchor_recovery_rate` |
| 证据完整率 | 等于 100% | `target_consistency.evidence_completeness_rate` |
| 三次结果一致率 | 不低于 90% | `target_consistency.consistency_rate` |
| 清单外动作次数 | 等于 0 | `target_consistency.off_list_action_count` |
| 高风险动作自动执行次数 | 等于 0 | `target_consistency.risk_auto_action_count` |

说明：真实“误点击率”需要人工抽查截图确认。平台当前自动统计的是清单外动作次数，高风险动作会进入跳过或人工确认，不自动点击。

## 2. 本阶段已完成能力

1. 目标巡检按清单执行，找不到目标时记录 `not_found`，不点击无关控件。
2. 支持最近 3 次执行一致性统计，后端统一输出 `target_consistency`。
3. 支持目标识别率、锚点恢复成功率、证据完整率、结果一致率等核心指标。
4. 加固 bounds 兜底，避免把 `android:id/content` 等整页容器误判为底部 TAB 或具体控件。
5. 点击后补充状态诊断，支持识别控件状态变化、弹窗出现/关闭、列表内容变化、页面跳转和页面结构变化。
6. 报告目标巡检矩阵展示命中依据、状态变化、变化依据、恢复状态、bounds 和坐标。
7. 已补回归测试覆盖目标解析、定位优先级、bounds 兜底、风险跳过、一致性指标、状态变化和页面级变化诊断。

## 3. 手工验收流程

### 3.1 前置条件

1. Android 手机已连接并可被 `adb devices` 识别。
2. QAFlow 后端和前端服务已启动。
3. 被测 APP 已安装，项目中已绑定正确包名。
4. 手机停留在目标巡检任务要求的起始页面。
5. 目标巡检任务配置 5 到 10 个目标控件，优先选择稳定入口、Tab、列表项、Switch、普通按钮。

### 3.2 执行步骤

1. 进入 `APP 自动化测试 / AI 探索测试`。
2. 创建或选择一个策略为 `目标巡检` 的任务。
3. 确认目标清单只包含本轮要验的控件。
4. 连续执行同一个任务 3 次，每次执行前确保手机回到同一业务起始页。
5. 打开该任务报告。
6. 在报告详情中查看目标巡检矩阵和目标稳定性。
7. 抽查每个目标的定位证据，确认截图框选和命中控件符合预期。

### 3.3 验收判定

如果 `target_consistency.passed = true`，并且人工抽查截图没有发现误点，可以认为该任务通过 P0 基线验收。

如果未通过，优先按以下顺序排查：

1. `run_count` 未通过：继续执行同一任务直到满 3 次。
2. `recognition_rate` 未通过：查看未命中目标截图，补语义元素或调整目标名称。
3. `anchor_recovery_rate` 未通过：检查点击后是否偏航，补返回策略或起始导航。
4. `evidence_completeness_rate` 未通过：检查截图、bounds、坐标和目标结果入库链路。
5. `consistency_rate` 未通过：对比三次目标状态，确认是否页面数据波动、设备状态不同或定位不稳定。
6. 高风险动作相关指标未通过：立即停止自动执行，检查风险护栏逻辑。

## 4. 重点场景验收

| 场景 | 预期 |
| --- | --- |
| 点击普通入口后页面跳转 | 目标状态为 `found_effective`，变化依据包含页面跳转或页面结构变化 |
| 点击 Switch 后页面不跳转 | 如 `checked/selected` 变化，应视为有效变化 |
| 点击后出现二级确认弹窗 | 变化依据包含弹窗出现 |
| 点击列表刷新或展开 | 变化依据包含列表内容变化 |
| 目标不存在 | 目标状态为 `not_found`，不点击清单外控件 |
| 命中退出、删除、支付等风险词 | 目标状态为 `risk_skipped` 或被风险护栏阻断，不自动点击 |
| bounds 兜底目标 | 不应命中整页容器，应命中合理面积控件或记录未找到 |

## 5. 自动化验证命令

```powershell
& 'E:\workspace\testhub_platform\venv\Scripts\python.exe' -m pytest apps/app_automation/tests/test_target_inspection_runner.py apps/app_automation/tests/test_inspection_metrics.py -q
& 'E:\workspace\testhub_platform\venv\Scripts\python.exe' manage.py check
cd E:\workspace\testhub_platform\frontend
npm run build
```

## 6. 本轮真机自测记录

执行记录：

1. `adb devices` 曾识别到设备 `3058818956000P4`。
2. 手机前台为 `com.example.qaflow.demo/.MainActivity`。
3. 使用任务 `32 / 社区首页 - 目标巡检` 创建真机执行批次 `run_id=17`。
4. 执行链路完成，结果为 `completed / warning`，总耗时约 `160.54s`。
5. 执行过程中状态诊断数据已落库，包含页面跳转、页面结构变化、控件状态变化和列表内容变化等证据。
6. 本轮发现任务目标重复执行问题：任务配置 6 个目标，但结构化目标、`target_list`、`entry_keywords` 被合并为 12 个执行目标。
7. 已修复目标清单去重逻辑：同名目标只保留第一份，优先保留结构化目标。
8. 修复后本地校验任务 32 目标队列为 6 个：`搜索view`、`可点击区域`、`打开社区列表`、`搜索社区、用户名称/ID`、`more图标`、`通知可点击区域`。

自测结论：

1. 真机执行链路可跑通，目标结果、截图证据、状态诊断和恢复状态均可入库。
2. 本轮冒烟未达到 P0 通过结论，因为执行前存在目标重复合并问题，已修复但受设备断连影响未能完成第二轮真机复跑。
3. 设备在执行完成后从 `adb devices` 列表消失，重启 ADB server 后仍未恢复，建议重新插拔 USB 或确认手机授权后复跑任务 32。
4. 复跑预期：任务 32 应只执行 6 个目标，不再出现 12 个目标的重复执行。

## 7. 当前边界

以下内容不属于 P0 已完成范围：

1. iOS 执行器。
2. 设备资源池和分布式调度。
3. AI 直接控制手机执行。
4. 页面地图版本差异和 UI 改版影响分析完整闭环。
5. 需求驱动自动化用例生成完整链路。

这些能力应在 P0 稳定后进入 P1/P2，不建议混入当前验收结论。
