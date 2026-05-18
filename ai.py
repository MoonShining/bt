"""
多周期趋势跟随策略
基于 SMA、RSI、成交量的综合判断策略
- 仅做多（不做空）
- 固定止损
- 分批止盈（金字塔式减仓）
- 短、中、长期趋势判断
"""

import backtrader as bt


class MultiPeriodTrendStrategy(bt.Strategy):
    """
    多周期趋势跟随策略

    入场条件（需同时满足）：
    1. 短期、中期、长期趋势一致向上：SMA5 > SMA20 > SMA60
    2. RSI 回调：RSI(14) 在 30-50 之间（逢低买入）
    3. 放量确认：成交量 > 成交量均线(20)

    风险管理：
    - 固定止损：入场价 × (1 - 止损比例)
    - 趋势反转止损：SMA5 下穿 SMA20

    分批止盈：
    - 盈利 > 20%：卖出 1/3
    - 盈利 > 40%：再卖 1/3
    - 盈利 > 60% 或趋势减弱：清仓
    """

    params = dict(
        # ── 均线指标（短期、中期、长期）──
        sma_short=5,          # 短期均线
        sma_mid=20,          # 中期均线
        sma_long=60,         # 长期均线

        # ── RSI 指标 ──
        rsi_period=14,
        rsi_low=30,           # RSI 低于此值视为超卖
        rsi_high=70,          # RSI 高于此值视为超买
        rsi_entry_max=50,     # RSI 高于此值不入场（避免追高）

        # ── 成交量指标 ──
        vol_ma_period=20,     # 成交量均线周期
        vol_multiplier=1.5,    # 放量倍数

        # ── 固定止损 ──
        stop_loss_pct=0.10,   # 固定止损比例（10%）

        # ── 分批止盈 ──
        tp1_pct=0.20,         # 第一止盈位
        tp1_ratio=0.33,       # 第一止盈卖出比例
        tp2_pct=0.40,         # 第二止盈位
        tp2_ratio=0.33,       # 第二止盈卖出比例
        tp3_pct=0.60,         # 第三止盈位（或清仓）

        # ── 仓位管理：基于趋势强度的动态风险 ──
        base_risk=0.01,       # 最小风险比例
        max_risk=0.04,        # 最大风险比例
        max_position=0.95,     # 最大仓位

        # ── 其他 ──
        verbose=True,
    )

    def __init__(self):
        # ── 短、中、长期均线 ──
        self.sma_short = bt.indicators.SimpleMovingAverage(period=self.p.sma_short)
        self.sma_mid = bt.indicators.SimpleMovingAverage(period=self.p.sma_mid)
        self.sma_long = bt.indicators.SimpleMovingAverage(period=self.p.sma_long)

        # ── RSI 指标 ──
        self.rsi = bt.indicators.RelativeStrengthIndex(period=self.p.rsi_period)

        # ── 成交量指标 ──
        self.vol_ma = bt.indicators.SimpleMovingAverage(self.data.volume, period=self.p.vol_ma_period)

        # ── 内部状态 ──
        self.order = None
        self.avg_entry_price = 0.0  # 平均建仓价格（支持多次建仓）
        self.total_shares = 0       # 累计持仓股数
        self.sl_price = None        # 止损价（基于平均成本）
        self.tp_levels = {
            'tp1': False,
            'tp2': False,
            'tp3': False,
        }

    # ─────── 趋势判断（短、中、长期一致）──
    def _is_uptrend(self) -> bool:
        """判断短、中、长期趋势一致向上"""
        return (
            self.sma_short[0] > self.sma_mid[0] and    # 短期 > 中期
            self.sma_mid[0] > self.sma_long[0]        # 中期 > 长期
        )

    # ─────── 放量判断 ───────
    def _is_volume_surge(self) -> bool:
        """判断是否放量"""
        if self.vol_ma[0] > 0:
            return self.data.volume[0] > self.vol_ma[0] * self.p.vol_multiplier
        return False

    # ─────── RSI 条件 ───────
    def _is_rsi_good(self) -> bool:
        """RSI 在合理区间（超卖但不超买）"""
        return (
            self.rsi[0] >= self.p.rsi_low and
            self.rsi[0] <= self.p.rsi_entry_max
        )

    # ─────── 计算趋势强度 ───────
    def _calc_trend_strength(self) -> float:
        """
        计算趋势强度（0-1），用于决定本次建仓的风险比例
        综合三个维度：
        1. 均线偏离度 - SMA5 相对 SMA60 偏离越大，趋势越强
        2. RSI 位置 - RSI 越低位，回调越充分，强度越高
        3. 放量程度 - 成交量相对均线放大越多，强度越高
        """
        # 1. 均线强度：(SMA5 - SMA60) / SMA60
        # 正常范围：0% ~ 15% → 归一化到 0-1
        ma_diff_pct = (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0]
        ma_strength = min(max(ma_diff_pct / 0.15, 0), 1)

        # 2. RSI 强度：RSI 在 [30, 50] 区间，越小越强
        # RSI=30 → 强度1，RSI=50 → 强度0
        rsi_range = self.p.rsi_entry_max - self.p.rsi_low
        if rsi_range > 0:
            rsi_strength = (self.p.rsi_entry_max - self.rsi[0]) / rsi_range
        else:
            rsi_strength = 1
        rsi_strength = min(max(rsi_strength, 0), 1)

        # 3. 成交量强度：成交量 / (vol_multiplier × vol_ma)
        # 正常范围：1 × ~ 3 × → 归一化到 0-1
        vol_threshold = self.p.vol_multiplier * self.vol_ma[0]
        if vol_threshold > 0:
            vol_ratio = self.data.volume[0] / vol_threshold
        else:
            vol_ratio = 1
        vol_strength = min(max(vol_ratio / 2, 0), 1)  # 2 倍阈值 → 强度 1

        # 综合强度：加权平均（均线 40%, RSI 30%, 成交量 30%）
        strength = 0.4 * ma_strength + 0.3 * rsi_strength + 0.3 * vol_strength

        return strength

    # ─────── 计算当前盈利比例 ───────
    def _calc_profit_pct(self) -> float:
        """计算当前持仓盈利比例（基于平均建仓成本）"""
        if self.avg_entry_price == 0:
            return 0
        return (self.data.close[0] - self.avg_entry_price) / self.avg_entry_price

    # ─────── 分批止盈逻辑 ───────
    def _check_take_profit(self):
        """检查是否触发分批止盈"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        profit_pct = self._calc_profit_pct()
        current_size = self.position.size

        # 第一止盈：盈利 20%，卖出 1/3
        if not self.tp_levels['tp1'] and profit_pct >= self.p.tp1_pct:
            sell_size = int(current_size * self.p.tp1_ratio)
            if sell_size > 0:
                self.log(f"第一止盈  盈利={profit_pct:.2%}  卖出={sell_size}")
                self.order = self.sell(size=sell_size)
                self.tp_levels['tp1'] = True

        # 第二止盈：盈利 40%，再卖 1/3
        elif self.tp_levels['tp1'] and not self.tp_levels['tp2'] and profit_pct >= self.p.tp2_pct:
            sell_size = int(current_size * self.p.tp2_ratio)
            if sell_size > 0:
                self.log(f"第二止盈  盈利={profit_pct:.2%}  卖出={sell_size}")
                self.order = self.sell(size=sell_size)
                self.tp_levels['tp2'] = True

        # 第三止盈：盈利 60% 或趋势减弱，清仓
        elif self.tp_levels['tp2'] and not self.tp_levels['tp3']:
            if profit_pct >= self.p.tp3_pct or not self._is_uptrend():
                self.log(f"第三止盈/趋势减弱  盈利={profit_pct:.2%}  清仓")
                self.close()
                self.tp_levels['tp3'] = True

    # ─────── 止损逻辑 ───────
    def _check_stop_loss(self):
        """检查止损条件"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        current_price = self.data.close[0]

        # 固定止损
        if current_price <= self.sl_price:
            self.log(f"触发固定止损  price={current_price:.2f}  sl={self.sl_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
            self.close()

        # 趋势反转止损：SMA5 下穿 SMA20
        elif self.sma_short[0] < self.sma_mid[0]:
            self.log(f"趋势反转止损  SMA5={self.sma_short[0]:.2f}  SMA20={self.sma_mid[0]:.2f}")
            self.close()

    # ─────── 入场逻辑 ───────
    def _check_entry_signal(self) -> bool:
        """检查是否满足入场条件"""
        # 1. 趋势向上（短、中、长期一致）
        if not self._is_uptrend():
            return False

        # 2. RSI 在合理区间
        if not self._is_rsi_good():
            return False

        # 3. 放量确认
        if not self._is_volume_surge():
            return False

        return True

    # ─────── 计算可建仓数量 ───────
    def _calc_available_size(self) -> int:
        """计算可新增建仓数量（考虑最大仓位限制，基于趋势强度动态调整风险）"""
        portfolio_value = self.broker.getvalue()
        current_shares = self.position.size
        current_value = current_shares * self.data.close[0]
        max_allowed_value = portfolio_value * self.p.max_position
        available_value = max_allowed_value - current_value

        if available_value <= 0:
            return 0

        # 计算趋势强度（0-1）
        strength = self._calc_trend_strength()

        # 根据趋势强度计算本次风险比例：base_risk ~ max_risk
        risk_range = self.p.max_risk - self.p.base_risk
        current_risk = self.p.base_risk + strength * risk_range

        # 使用风险计算仓位大小
        # 使用当前价格预估，实际止损会在成交后更新
        est_entry = self.data.close[0]
        risk_amount = portfolio_value * current_risk
        sl_dist = est_entry * self.p.stop_loss_pct
        if sl_dist > 0:
            size_from_risk = int(risk_amount / sl_dist)
        else:
            size_from_risk = 0

        # 不能超过可用额度
        size_from_available = int(available_value / est_entry)

        size = min(size_from_risk, size_from_available)

        if self.p.verbose and size > 0:
            self.log(f"趋势强度={strength:.2f}  风险比例={current_risk:.1%}  建仓规模={size}")

        return size

    # ─────── 主逻辑 ───────
    def next(self):
        # 有挂单时不操作
        if self.order:
            return

        # 有持仓时：先检查止损止盈
        if self.position.size > 0:
            self._check_stop_loss()
            self._check_take_profit()

        # 无论是否已有持仓，只要满足信号且还有加仓空间，就可以加仓（支持多次建仓）
        if self._check_entry_signal():
            size = self._calc_available_size()

            if size <= 0:
                return

            # 记录下单前状态，成交后会更新平均成本
            self.total_shares = self.position.size
            self.log(
                f"建仓  est_price={self.data.close[0]:.2f}  size={size}  "
                f"RSI={self.rsi[0]:.2f}  "
                f"SMA5={self.sma_short[0]:.2f}  SMA20={self.sma_mid[0]:.2f}  SMA60={self.sma_long[0]:.2f}"
            )
            self.order = self.buy(size=size)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order.isbuy():
                # 买入成交：更新平均建仓成本（支持多次建仓）
                executed_price = order.executed.price
                executed_size = order.executed.size
                old_shares = self.total_shares  # 成交前股数
                new_shares = old_shares + executed_size

                if old_shares == 0:
                    # 首次建仓
                    self.avg_entry_price = executed_price
                else:
                    # 加仓：重新计算平均成本
                    self.avg_entry_price = (
                        (self.avg_entry_price * old_shares) + (executed_price * executed_size)
                    ) / new_shares

                self.total_shares = new_shares

                # 更新止损价（基于最新平均成本）
                self.sl_price = self.avg_entry_price * (1 - self.p.stop_loss_pct)

                self.log(
                    f"买入成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"avg_entry={self.avg_entry_price:.2f}  "
                    f"sl={self.sl_price:.2f}  "
                    f"total_shares={self.total_shares}"
                )
            else:
                # 卖出成交：如果是部分卖出，平均成本不变；如果全部卖出，重置状态
                executed_price = order.executed.price
                executed_size = abs(order.executed.size)
                remaining_shares = self.total_shares - executed_size

                self.log(
                    f"卖出成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"remaining_shares={remaining_shares}"
                )

                # 全部卖出后重置状态
                if remaining_shares == 0:
                    self.avg_entry_price = 0.0
                    self.total_shares = 0
                    self.sl_price = None
                    self.tp_levels = {'tp1': False, 'tp2': False, 'tp3': False}
                else:
                    self.total_shares = remaining_shares

        elif order.status in (order.Canceled, order.Rejected, order.Margin):
            self.log(f"订单失败  status={order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            pnl_pct = (trade.pnl / trade.value) * 100 if trade.value > 0 else 0
            self.log(
                f"交易结束  PnL={trade.pnl:.2f}  "
                f"PneL%={pnl_pct:.2f}%  "
                f"comm={trade.pnlcomm:.2f}"
            )

    def log(self, txt):
        if self.p.verbose:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")


# 兼容旧的策略类名
TrendFollowStrategy = MultiPeriodTrendStrategy
