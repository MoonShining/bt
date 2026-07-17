# Trend Following ATR Exits 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 `TrendFollowingStrategy` 添加 ATR 硬止损和趋势反转后的两段退出。

**架构：** 退出逻辑保留在 `strategy/trend_following.py` 内部，按 data feed 维护入场价、止损线、最高收盘价和反转退出阶段。测试用合成 Backtrader 数据驱动完整策略运行，并通过订单成交记录验证退出规模。

**技术栈：** Python、Backtrader、unittest、pandas。

---

## 文件结构

- 修改：`strategy/trend_following.py`，添加 ATR 指标、持仓退出状态和退出规则。
- 创建：`test_trend_following.py`，添加趋势策略的合成数据回归测试。

## 任务 1：ATR 止损

**文件：**
- 修改：`strategy/trend_following.py`
- 创建：`test_trend_following.py`

- [ ] **步骤 1：编写失败的测试**

在 `test_trend_following.py` 中创建 Backtrader 合成数据测试，使用短 ATR/均线周期，让策略先买入，再在价格跌破止损线时清仓：

```python
def test_atr_stop_closes_full_position(self):
    bars = [
        (10, 11, 9, 10),
        (11, 12, 10, 11),
        (12, 13, 11, 12),
        (13, 14, 12, 13),
        (14, 15, 13, 14),
        (15, 16, 14, 15),
        (16, 17, 15, 16),
        (16, 17, 7, 8),
        (8, 9, 7, 8),
    ]
    strategy = run_strategy(
        bars,
        fast_period=2,
        slow_period=3,
        atr_period=2,
        atr_multiplier=1.0,
    )

    sells = [event for event in strategy.order_events if event["side"] == "sell"]

    self.assertTrue(sells)
    self.assertEqual(strategy.getposition(strategy.datas[0]).size, 0)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m unittest test_trend_following.TrendFollowingStrategyTest.test_atr_stop_closes_full_position -v`

预期：FAIL，原因是 `atr_period`/`atr_multiplier` 参数或止损行为尚不存在。

- [ ] **步骤 3：编写最少实现代码**

在策略中添加 ATR 指标和止损状态。买单成交后记录入场状态；持仓期间更新只上移的止损线；收盘价低于止损线时 `close(data=data)`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m unittest test_trend_following.TrendFollowingStrategyTest.test_atr_stop_closes_full_position -v`

预期：PASS。

## 任务 2：趋势反转两段退出

**文件：**
- 修改：`strategy/trend_following.py`
- 修改：`test_trend_following.py`

- [ ] **步骤 1：编写失败的测试**

添加测试：第一次反转卖出约半仓，下一根仍反转卖出剩余仓位。

```python
def test_reversal_exits_half_then_remainder(self):
    bars = [
        (10, 10.5, 9.5, 10),
        (11, 11.5, 10.5, 11),
        (12, 12.5, 11.5, 12),
        (13, 13.5, 12.5, 13),
        (14, 14.5, 13.5, 14),
        (13, 13.5, 12.5, 13),
        (12, 12.5, 11.5, 12),
        (11, 11.5, 10.5, 11),
    ]
    strategy = run_strategy(
        bars,
        fast_period=2,
        slow_period=3,
        atr_period=2,
        atr_multiplier=10.0,
    )

    sells = [event for event in strategy.order_events if event["side"] == "sell"]

    self.assertGreaterEqual(len(sells), 2)
    self.assertEqual(strategy.getposition(strategy.datas[0]).size, 0)
    self.assertGreater(sells[0]["size"], 0)
    self.assertGreater(sells[1]["size"], 0)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m unittest test_trend_following.TrendFollowingStrategyTest.test_reversal_exits_half_then_remainder -v`

预期：FAIL，原因是当前趋势反转未分两段退出。

- [ ] **步骤 3：编写最少实现代码**

添加反转判断和每个 data feed 的 `reversal_exit_steps`。第一次反转卖出 `max(1, abs(position.size) // 2)`，第二次仍反转时清仓。趋势恢复时重置阶段。

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m unittest test_trend_following.TrendFollowingStrategyTest.test_reversal_exits_half_then_remainder -v`

预期：PASS。

## 任务 3：趋势恢复重置阶段

**文件：**
- 修改：`strategy/trend_following.py`
- 修改：`test_trend_following.py`

- [ ] **步骤 1：编写失败的测试**

添加测试：第一次反转卖半仓后趋势恢复，之后再次反转应重新从半仓退出开始。

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m unittest test_trend_following.TrendFollowingStrategyTest.test_reversal_recovery_resets_staged_exit -v`

预期：FAIL，原因是恢复重置尚未实现。

- [ ] **步骤 3：编写最少实现代码**

当持仓且趋势不反转时，将该 data feed 的反转退出阶段重置为 0。

- [ ] **步骤 4：运行完整测试**

运行：`python3 -m unittest -v`

预期：所有测试 PASS。
