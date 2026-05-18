"""
多因子趋势跟随策略
基于趋势、RSI、成交量、K线形态的综合判断策略
- 仅做多（不做空）
- 动态止损（ATR）
- 分批止盈（金字塔式减仓）
- 放量确认
- 强烈K线形态增强信号
"""

import backtrader as bt
try:
    import backtrader.talib as btalib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False


class MultiFactorTrendStrategy(bt.Strategy):
    """
    多因子趋势跟随策略

    入场条件（需同时满足）：
    1. 趋势向上：EMA20 > EMA60 且 ADX > 25
    2. RSI 回调：RSI(14) 在 30-50 之间（逢低买入）
    3. 放量确认：成交量 > 成交量均线(20)
    4. K线形态：出现强烈看涨形态（三个白武士、早晨之星、刺透形态等）

    风险管理：
    - 初始止损：入场价 - ATR(14) × 2.5
    - 追踪止损：盈利 > 15% 后启用，止损价 = 最高价 - ATR × 2.0
    - 趋势止损：EMA20 下穿 EMA60 时止损

    分批止盈：
    - 盈利 > 20%：卖出 1/3
    - 盈利 > 40%：再卖 1/3
    - 盈利 > 60% 或趋势减弱：清仓
    """

    params = dict(
        # ── 趋势指标 ──
        ema_fast=20,
        ema_slow=60,
        adx_period=14,
        adx_threshold=20,       # 降低 ADX 阈值

        # ── RSI 指标 ──
        rsi_period=14,
        rsi_low=35,           # 提高 RSI 低阈值
        rsi_high=70,          # RSI 高于此值视为超买
        rsi_entry_max=60,     # 提高 RSI 入场上限

        # ── 成交量指标 ──
        vol_ma_period=20,     # 成交量均线周期
        vol_multiplier=1.2,    # 降低放量倍数

        # ── K线形态 ──
        use_patterns=True,     # 是否使用K线形态
        min_bullish=1,        # 降低最少看涨形态数量

        # ── 止损止盈 ──
        atr_period=14,
        atr_sl_mult=2.0,      # 降低止损倍数
        atr_trail_mult=1.5,   # 降低追踪止损倍数
        trail_after_pct=0.10,  # 降低启用追踪止损的盈利比例

        # ── 分批止盈 ──
        tp1_pct=0.20,         # 第一止盈位
        tp1_ratio=0.33,       # 第一止盈卖出比例
        tp2_pct=0.40,         # 第二止盈位
        tp2_ratio=0.33,       # 第二止盈卖出比例
        tp3_pct=0.60,         # 第三止盈位（或清仓）

        # ── 仓位管理 ──
        base_risk=0.02,       # 基础风险比例
        max_position=0.95,     # 最大仓位

        # ── 其他 ──
        verbose=True,
    )

    def __init__(self):
        # ── 趋势指标 ──
        self.ema_fast = bt.indicators.ExponentialMovingAverage(period=self.p.ema_fast)
        self.ema_slow = bt.indicators.ExponentialMovingAverage(period=self.p.ema_slow)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(period=self.p.adx_period)

        # ── RSI 指标 ──
        self.rsi = bt.indicators.RelativeStrengthIndex(period=self.p.rsi_period)

        # ── 成交量指标 ──
        self.vol_ma = bt.indicators.SimpleMovingAverage(self.data.volume, period=self.p.vol_ma_period)

        # ── ATR（用于止损） ──
        self.atr = bt.indicators.AverageTrueRange(period=self.p.atr_period)

        # K线形态识别（使用 TA-Lib）
        if HAS_TALIB and self.p.use_patterns:
            self.bullish_patterns = {
                '3WHITESOLDIERS': btalib.CDL3WHITESOLDIERS(self.data.open, self.data.high, self.data.low, self.data.close),
                'MORNINGSTAR': btalib.CDLMORNINGSTAR(self.data.open, self.data.high, self.data.low, self.data.close),
                'MORNINGDOJISTAR': btalib.CDLMORNINGDOJISTAR(self.data.open, self.data.high, self.data.low, self.data.close),
                'PIERCING': btalib.CDLPIERCING(self.data.open, self.data.high, self.data.low, self.data.close),
                'HAMMER': btalib.CDLHAMMER(self.data.open, self.data.high, self.data.low, self.data.close),
                'ENGULFING': btalib.CDLENGULFING(self.data.open, self.data.high, self.data.low, self.data.close),
                '3INSIDE': btalib.CDL3INSIDE(self.data.open, self.data.high, self.data.low, self.data.close),
                '3OUTSIDE': btalib.CDL3OUTSIDE(self.data.open, self.data.high, self.data.low, self.data.close),
                'ABANDONEDBABY': btalib.CDLABANDONEDBABY(self.data.open, self.data.high, self.data.low, self.data.close),
                'CONCEALBABYSWALL': btalib.CDLCONCEALBABYSWALL(self.data.open, self.data.high, self.data.low, self.data.close),
            }
        else:
            self.bullish_patterns = {}

        # ── 内部状态 ──
        self.order = None
        self.entry_price = None
        self.sl_price = None
        self.tp_levels = {
            'tp1': False,
            'tp2': False,
            'tp3': False,
        }
        self.highest_price = None
        self.trailing = False
        self.trail_price = None

        # ── 统计 ──
        self.total_trades = 0
        self.winning_trades = 0

    # ─────── 检查强烈看涨K线形态 ───────
    def _check_bullish_pattern(self) -> int:
        """返回看涨形态数量"""
        if not self.p.use_patterns or not self.bullish_patterns:
            return 0

        bullish_count = 0

        # 检查每个看涨形态（值>0表示出现）
        for name, pattern in self.bullish_patterns.items():
            if pattern[0] > 0:
                bullish_count += 1
                if self.p.verbose:
                    print(f"[{self.data.datetime.date(0)}] 看涨形态: {name}")

        return bullish_count

    # ─────── 趋势判断 ───────
    def _is_uptrend(self) -> bool:
        """判断是否处于上涨趋势"""
        return (
            self.ema_fast[0] > self.ema_slow[0] and    # 多头排列
            self.adx[0] >= self.p.adx_threshold         # 有明确趋势
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

    # ─────── 计算仓位 ───────
    def _calc_position_size(self) -> int:
        """根据风险和 ATR 计算仓位"""
        portfolio_value = self.broker.getvalue()
        risk_amount = portfolio_value * self.p.base_risk

        # 每手风险 = 止损距离
        sl_dist = self.atr[0] * self.p.atr_sl_mult
        if sl_dist > 0:
            size = int(risk_amount / sl_dist)
        else:
            size = 0

        # 限制最大仓位
        max_size = int(portfolio_value * self.p.max_position / self.data.close[0])
        return min(size, max_size)

    # ─────── 计算当前盈利比例 ───────
    def _calc_profit_pct(self) -> float:
        """计算当前持仓盈利比例"""
        if not self.entry_price or self.entry_price == 0:
            return 0
        return (self.data.close[0] - self.entry_price) / self.entry_price

    # ─────── 分批止盈逻辑 ───────
    def _check_take_profit(self):
        """检查是否触发分批止盈"""
        if not self.entry_price or self.position.size == 0:
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
        if not self.entry_price:
            return

        current_price = self.data.close[0]

        # 更新最高价
        if self.highest_price is None:
            self.highest_price = current_price
        elif current_price > self.highest_price:
            self.highest_price = current_price

        # 转为追踪止损
        profit_pct = self._calc_profit_pct()
        if not self.trailing and profit_pct >= self.p.trail_after_pct:
            self.trailing = True
            self.trail_price = self.highest_price - self.atr[0] * self.p.atr_trail_mult
            self.log(f"启用追踪止损  trail={self.trail_price:.2f}")

        # 更新追踪止损价（只上移不下不下移）
        if self.trailing:
            new_trail = self.highest_price - self.atr[0] * self.p.atr_trail_mult
            if new_trail > self.trail_price:
                self.trail_price = new_trail

        # 判断触发止损
        active_sl = self.trail_price if self.trailing else self.sl_price

        if current_price <= active_sl:
            sl_type = "追踪止损" if self.trailing else "初始止损"
            self.log(f"触发{sl_type}  price={current_price:.2f}  sl={active_sl:.2f}")
            self.close()

        # 趋势反转止损：EMA20 下穿 EMA60
        elif self.ema_fast[0] < self.ema_slow[0]:
            self.log(f"趋势反转止损  EMA20={self.ema_fast[0]:.2f}  EMA60={self.ema_slow[0]:.2f}")
            self.close()

        # RSI 超买后回落止损
        elif self.rsi[0] > self.p.rsi_high and self.rsi[-1] <= self.p.rsi_high:
            self.log(f"RSI超买回落止损  RSI={self.rsi[0]:.2f}")
            self.close()

    # ─────── 入场逻辑 ───────
    def _check_entry_signal(self) -> bool:
        """检查是否满足入场条件"""
        # 1. 趋势向上
        uptrend = self._is_uptrend()
        if not uptrend:
            return False

        # 2. RSI 在合理区间
        rsi_good = self._is_rsi_good()
        if not rsi_good:
            return False

        # 3. 放量确认
        volume_surge = self._is_volume_surge()
        if not volume_surge:
            return False

        # 4. 看涨 K 线形态
        bullish_count = self._check_bullish_pattern()
        if self.p.use_patterns and bullish_count < self.p.min_bullish:
            return False

        return True

    # ─────── 主逻辑 ───────
    def next(self):
        # 有挂单时不操作
        if self.order:
            return

        # 有持仓时：检查止损止盈
        if self.position.size > 0:
            self._check_stop_loss()
            self._check_take_profit()
            return

        # 无持仓时：检查入场
        if self._check_entry_signal():
            size = self._calc_position_size()

            if size <= 0:
                return

            # 计算止损止盈价格
            entry_price = self.data.close[0]
            atr_val = self.atr[0]

            self.entry_price = entry_price
            self.sl_price = entry_price - atr_val * self.p.atr_sl_mult
            self.highest_price = entry_price
            self.trailing = False
            self.trail_price = None

            # 重置止盈状态
            self.tp_levels = {'tp1': False, 'tp2': False, 'tp3': False}

            # 开仓
            self.log(
                f"开仓  price={entry_price:.2f}  size={size}  "
                f"SL={self.sl_price:.2f}  RSI={self.rsi[0]:.2f}  "
                f"ADX={self.adx[0]:.2f}"
            )
            self.order = self.buy(size=size)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.total_trades += 1
                self.log(
                    f"买入成交  price={order.executed.price:.2f}  "
                    f"size={order.executed.size}  "
                    f"cost={order.executed.value:.2f}"
                )
            else:
                self.log(
                    f"卖出成交  price={order.executed.price:.2f}  "
                    f"size={order.executed.size}  "
                    f"value={order.executed.value:.2f}"
                )

                # 更新统计
                pnl = order.executed.pnl
                if pnl > 0:
                    self.winning_trades += 1
        elif order.status in (order.Canceled, order.Rejected, order.Margin):
            self.log(f"订单失败  status={order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            pnl_pct = (trade.pnl / trade.value) * 100 if trade.value > 0 else 0
            self.log(
                f"交易结束  PnL={trade.pnl:.2f}  "
                f"PnL%={pnl_pct:.2f}%  "
                f"comm={trade.pnlcomm:.2f}"
            )

    def log(self, txt):
        if self.p.verbose:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")


# 兼容旧的策略类名
TrendFollowStrategy = MultiFactorTrendStrategy
