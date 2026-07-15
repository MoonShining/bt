# ETF 双动量轮动策略实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将当前均线交叉回测替换为单一 ETF 双动量轮动策略。

**架构：** `main.py` 保持项目的单入口结构，新增 `DualMomentumRotationStrategy` 并让 `run_backtest()` 总是使用它。`BacktestConfig` 移除固定手数和均线参数，改为轮动参数；`test_main.py` 用合成 CSV 验证动量选择、空仓过滤和 CLI 参数。

**技术栈：** Python、Backtrader、Pandas、unittest、argparse。

---

## 文件结构

- 修改：`main.py`
  - 移除 `MovingAverageCrossStrategy`。
  - 新增 `DualMomentumRotationStrategy`。
  - 更新 `BacktestConfig`、`run_backtest()`、CLI 参数和 `main()` 配置传递。
- 修改：`test_main.py`
  - 保留数据抓取和 CSV 写入测试。
  - 更新 `run_backtest()` 配置测试。
  - 新增轮动策略和 CLI 参数测试。

## 任务 1：更新配置和 CLI 测试

**文件：**
- 修改：`test_main.py`

- [ ] **步骤 1：编写失败的 CLI 测试**

在 `MainTest` 中新增：

```python
    def test_parser_exposes_rotation_parameters_only(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "--symbols",
                "161226,513100",
                "--start",
                "2024-01-01",
                "--end",
                "2024-12-31",
                "--momentum-period",
                "90",
                "--rebalance-period",
                "15",
                "--min-momentum",
                "0.02",
            ]
        )

        self.assertEqual(args.momentum_period, 90)
        self.assertEqual(args.rebalance_period, 15)
        self.assertEqual(args.min_momentum, 0.02)
        self.assertFalse(hasattr(args, "stake"))
        self.assertFalse(hasattr(args, "fast_period"))
        self.assertFalse(hasattr(args, "slow_period"))
```

同时更新 import：

```python
from main import BacktestConfig, build_parser, fetch_funds_to_csv, run_backtest, write_backtrader_csv
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python3 -m unittest test_main.MainTest.test_parser_exposes_rotation_parameters_only
```

预期：FAIL，报错包含 `unrecognized arguments: --momentum-period ...` 或旧参数仍存在。

- [ ] **步骤 3：更新 `BacktestConfig` 和 CLI**

在 `main.py` 中把 `BacktestConfig` 改为：

```python
@dataclass(frozen=True)
class BacktestConfig:
    cash: float = 100000.0
    commission: float = 0.001
    momentum_period: int = 60
    rebalance_period: int = 20
    min_momentum: float = 0.0
```

在 `build_parser()` 中删除：

```python
    parser.add_argument("--stake", type=int, default=100, help="每次买入固定份额")
    parser.add_argument("--fast-period", type=int, default=10, help="快均线周期")
    parser.add_argument("--slow-period", type=int, default=30, help="慢均线周期")
```

并添加：

```python
    parser.add_argument("--momentum-period", type=int, default=60, help="动量回看交易日数")
    parser.add_argument("--rebalance-period", type=int, default=20, help="轮动调仓间隔交易日数")
    parser.add_argument("--min-momentum", type=float, default=0.0, help="绝对动量最低阈值")
```

在 `main()` 中构造配置时改为：

```python
        config=BacktestConfig(
            cash=args.cash,
            commission=args.commission,
            momentum_period=args.momentum_period,
            rebalance_period=args.rebalance_period,
            min_momentum=args.min_momentum,
        ),
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python3 -m unittest test_main.MainTest.test_parser_exposes_rotation_parameters_only
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add main.py test_main.py
git commit -m "test: cover ETF rotation CLI parameters"
```

## 任务 2：实现双动量轮动策略

**文件：**
- 修改：`main.py`
- 修改：`test_main.py`

- [ ] **步骤 1：编写失败的正动量选择测试**

在 `test_main.py` 中新增 helper：

```python
def _write_price_csv(path: Path, prices: list[float]) -> None:
    dataframe = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(prices), freq="D"),
            "open": prices,
            "high": [price + 0.1 for price in prices],
            "low": [price - 0.1 for price in prices],
            "close": prices,
            "volume": [1000] * len(prices),
            "openinterest": [0] * len(prices),
        }
    )
    dataframe.to_csv(path, index=False)
```

在 `MainTest` 中新增：

```python
    def test_dual_momentum_rotates_into_strongest_positive_etf(self):
        with _tmpdir() as tmp_path:
            weak_path = tmp_path / "weak_daily.csv"
            strong_path = tmp_path / "strong_daily.csv"
            _write_price_csv(weak_path, [10.0] * 80)
            _write_price_csv(strong_path, [10.0 + index * 0.2 for index in range(80)])

            result = run_backtest(
                csv_paths=[weak_path, strong_path],
                config=BacktestConfig(
                    cash=100000,
                    commission=0.0,
                    momentum_period=20,
                    rebalance_period=5,
                    min_momentum=0.0,
                ),
            )

            self.assertEqual(result.symbols, ["weak", "strong"])
            self.assertGreater(result.end_value, result.start_value)
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python3 -m unittest test_main.MainTest.test_dual_momentum_rotates_into_strongest_positive_etf
```

预期：FAIL，因为当前仍使用均线交叉策略或 `BacktestConfig` 参数不匹配。

- [ ] **步骤 3：替换策略实现**

在 `main.py` 中删除 `MovingAverageCrossStrategy`，新增：

```python
class DualMomentumRotationStrategy(bt.Strategy):
    params = (
        ("momentum_period", 60),
        ("rebalance_period", 20),
        ("min_momentum", 0.0),
        ("cash_buffer", 0.995),
    )

    def __init__(self):
        self.orders = {}
        self.bar_count = 0
        for data in self.datas:
            self.orders[data] = None

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.orders[order.data] = None

    def next(self):
        if any(order is not None for order in self.orders.values()):
            return

        self.bar_count += 1
        if self.bar_count % self.p.rebalance_period != 0:
            return
        if any(len(data) <= self.p.momentum_period for data in self.datas):
            return

        selected = self._select_data()
        for data in self.datas:
            position = self.getposition(data)
            if position and data is not selected:
                self.orders[data] = self.close(data=data)

        if selected is None:
            return
        if self.getposition(selected):
            return

        cash = self.broker.getcash() * self.p.cash_buffer
        price = selected.close[0]
        if price <= 0:
            return
        size = int(cash / price)
        if size > 0:
            self.orders[selected] = self.buy(data=selected, size=size)

    def _select_data(self):
        ranked = []
        for data in self.datas:
            past_close = data.close[-self.p.momentum_period]
            current_close = data.close[0]
            if past_close <= 0:
                continue
            momentum = current_close / past_close - 1
            if momentum > self.p.min_momentum:
                ranked.append((momentum, data))

        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]
```

在 `run_backtest()` 中删除固定 sizer：

```python
    cerebro.addsizer(bt.sizers.FixedSize, stake=config.stake)
```

把 `cerebro.addstrategy(...)` 改为：

```python
    cerebro.addstrategy(
        DualMomentumRotationStrategy,
        momentum_period=config.momentum_period,
        rebalance_period=config.rebalance_period,
        min_momentum=config.min_momentum,
    )
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python3 -m unittest test_main.MainTest.test_dual_momentum_rotates_into_strongest_positive_etf
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add main.py test_main.py
git commit -m "feat: add ETF dual momentum rotation strategy"
```

## 任务 3：覆盖绝对动量空仓行为

**文件：**
- 修改：`test_main.py`

- [ ] **步骤 1：编写失败的空仓测试**

在 `MainTest` 中新增：

```python
    def test_dual_momentum_stays_in_cash_when_no_etf_has_positive_momentum(self):
        with _tmpdir() as tmp_path:
            first_path = tmp_path / "first_daily.csv"
            second_path = tmp_path / "second_daily.csv"
            _write_price_csv(first_path, [10.0 - index * 0.02 for index in range(80)])
            _write_price_csv(second_path, [20.0 - index * 0.03 for index in range(80)])

            result = run_backtest(
                csv_paths=[first_path, second_path],
                config=BacktestConfig(
                    cash=100000,
                    commission=0.0,
                    momentum_period=20,
                    rebalance_period=5,
                    min_momentum=0.0,
                ),
            )

            self.assertEqual(result.start_value, 100000)
            self.assertEqual(result.end_value, 100000)
            self.assertEqual(result.total_return, 0.0)
```

- [ ] **步骤 2：运行测试验证失败或通过**

运行：

```bash
python3 -m unittest test_main.MainTest.test_dual_momentum_stays_in_cash_when_no_etf_has_positive_momentum
```

预期：如果任务 2 已完整实现，可能直接 PASS；如果失败，通常是没有在 `selected is None` 时清仓或动量阈值使用了 `>=`。

- [ ] **步骤 3：修正空仓过滤**

如测试失败，确保 `_select_data()` 只接受：

```python
if momentum > self.p.min_momentum:
    ranked.append((momentum, data))
```

并确保 `next()` 在 `selected is None` 时只执行已有持仓平仓，不开新仓：

```python
if selected is None:
    return
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python3 -m unittest test_main.MainTest.test_dual_momentum_stays_in_cash_when_no_etf_has_positive_momentum
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add main.py test_main.py
git commit -m "test: cover ETF rotation cash filter"
```

## 任务 4：更新现有回测测试并全量验证

**文件：**
- 修改：`test_main.py`
- 修改：`main.py`

- [ ] **步骤 1：更新旧的 `run_backtest` 测试配置**

把现有 `test_run_backtest_loads_csv_files_and_returns_summary` 中的配置：

```python
config=BacktestConfig(cash=100000, commission=0.001, stake=100),
```

改为：

```python
config=BacktestConfig(
    cash=100000,
    commission=0.001,
    momentum_period=20,
    rebalance_period=5,
    min_momentum=0.0,
),
```

- [ ] **步骤 2：运行全量单元测试**

运行：

```bash
python3 -m unittest
```

预期：PASS，所有测试通过。

- [ ] **步骤 3：运行单文件烟测回测**

运行：

```bash
python3 main.py --symbols 161226 --start 2024-01-01 --end 2024-12-31 --output-dir data --momentum-period 20 --rebalance-period 5
```

预期：命令退出码为 0，输出包含：

```text
基金代码: 161226
初始资金:
结束资金:
总收益率:
最大回撤:
```

- [ ] **步骤 4：检查工作区和最终差异**

运行：

```bash
git status --short
git diff -- main.py test_main.py
```

预期：只包含本任务相关修改。

- [ ] **步骤 5：Commit**

```bash
git add main.py test_main.py
git commit -m "test: verify ETF rotation backtest"
```

## 自检

- 规格覆盖度：计划覆盖均线策略移除、双动量排名、绝对动量空仓、参数替换、测试和烟测。
- 占位符扫描：没有 `TODO`、`待定` 或未定义的“后续实现”步骤。
- 类型一致性：计划中统一使用 `DualMomentumRotationStrategy`、`momentum_period`、`rebalance_period`、`min_momentum` 和现有 `BacktestResult`。
