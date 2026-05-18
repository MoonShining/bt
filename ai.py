"""
多周期趋势跟随策略
基于 SMA、RSI、成交量的综合判断策略
- 支持做多和做空双向交易
- 固定止损
- 分批止盈（金字塔式减仓）
- 短、中、长期趋势判断
"""

import backtrader as bt


class MultiPeriodTrendStrategy(bt.Strategy):
    """
    多周期趋势跟随策略（支持双向交易）

    做多入场条件（需同时满足）：
    1. 短期、中期、长期趋势一致向上：SMA10 > SMA30 > SMA60
    2. RSI 回调：RSI(14) 在 30-65 之间（逢低买入）
    3. 放量确认：成交量 > 1.0 × 成交量均线(20)

    做空入场条件（需同时满足，完全对称）：
    1. 短期、中期、长期趋势一致向下：SMA10 < SMA30 < SMA60
    2. RSI 反弹：RSI(14) 在 35-70 之间（逢高做空）
    3. 放量确认：成交量 > 1.0 × 成交量均线(20)

    风险管理：
    - 做多固定止损：平均建仓成本 × (1 - 止损比例)
    - 做空固定止损：平均建仓成本 × (1 + 止损比例)
    - 趋势反转止损：SMA交叉即清仓
    - 动态风险：根据趋势强度，每次建仓风险 base_risk% ~ max_risk% 不等

    分批止盈：
    - 做多：盈利 > 15% 卖 1/3，> 30% 再卖 1/3，> 50% 或趋势反转清仓
    - 做空：盈利 > 15% 平 1/3，> 30% 再平 1/3，> 50% 或趋势反转清仓
    """

    params = dict(
        # ── 均线指标（短期、中期、长期）──
        sma_short=10,         # 短期均线
        sma_mid=30,          # 中期均线
        sma_long=60,         # 长期均线

        # ── RSI 指标 ──
        rsi_period=14,
        # 做多 RSI 区间
        rsi_long_low=30,     # RSI 低于此值视为超卖（适合做多）
        rsi_long_max=60,     # RSI 高于此值不入场做多（避免追高）【优化：从65收紧到60，过滤追高】
        # 做空 RSI 区间
        rsi_short_min=35,    # RSI 低于此值不入场做空（避免追空）
        rsi_short_high=70,   # RSI 高于此值视为超买（适合做空）

        # ── 成交量指标 ──
        vol_ma_period=20,     # 成交量均线周期
        vol_multiplier=1.2,   # 放量倍数【优化：从1.0提高到1.2，要求温和放量，比原来严但不过分】

        # ── 止损设置 ──
        stop_loss_pct=0.08,   # 初始固定止损比例
        # ── 跟踪止损 ──
        use_trailing_stop=True,  # 【新增】启用跟踪止损
        trailing_stop_pct=0.08,  # 跟踪止损回撤比例（从最高点回撤8%止损，放宽一点）

        # ── 分批止盈 ──
        tp1_pct=0.20,         # 第一止盈位【优化：从15%提高到20%】
        tp1_ratio=0.33,       # 第一止盈卖出/平仓比例
        tp2_pct=0.40,         # 第二止盈位【优化：从30%提高到40%】
        tp2_ratio=0.33,       # 第二止盈卖出/平仓比例
        tp3_pct=0.60,         # 第三止盈位（或清仓）【优化：从50%提高到60%】

        # ── 仓位管理：基于趋势强度的动态风险 ──
        base_risk=0.015,      # 最小风险比例【优化：从0.02微调，平衡风险】
        max_risk=0.07,        # 最大风险比例【优化：从0.08降到0.07，比原来保守】
        max_position=0.95,    # 最大仓位（占总资金比例）

        # ── MACD 趋势过滤 ──【新增】
        use_macd_filter=False,  # 启用MACD趋势过滤【默认关闭，可手动开启】
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,

        # ── 双向交易开关 ──
        allow_short=False,     # 是否允许做空
        allow_long=True,      # 是否允许做多

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

        # ── MACD 趋势过滤【新增】 ──
        if self.p.use_macd_filter:
            self.macd = bt.indicators.MACD(
                self.data,
                period_me1=self.p.macd_fast,
                period_me2=self.p.macd_slow,
                period_signal=self.p.macd_signal
            )

        # ── 内部状态 ──
        self.order = None
        self.avg_entry_price = 0.0  # 平均建仓价格
        self.total_shares = 0       # 累计持仓股数（绝对值，做多做空都用正数记录）
        self.sl_price = None        # 止损价
        self.highest_price = None   # 【新增】持仓以来最高价，用于跟踪止损
        self.position_type = None   # 'long' / 'short' / None
        self.tp_levels = {
            'tp1': False,
            'tp2': False,
            'tp3': False,
        }

    # ─────── 趋势判断 ───────
    def _is_uptrend(self) -> bool:
        """判断短、中、长期趋势一致向上"""
        return (
            self.sma_short[0] > self.sma_mid[0] and    # 短期 > 中期
            self.sma_mid[0] > self.sma_long[0]         # 中期 > 长期
        )

    def _is_downtrend(self) -> bool:
        """判断短、中、长期趋势一致向下"""
        return (
            self.sma_short[0] < self.sma_mid[0] and    # 短期 < 中期
            self.sma_mid[0] < self.sma_long[0]         # 中期 < 长期
        )

    # ─────── 放量判断 ───────
    def _is_volume_surge(self) -> bool:
        """判断是否放量"""
        if self.vol_ma[0] > 0:
            return self.data.volume[0] > self.vol_ma[0] * self.p.vol_multiplier
        return False

    # ─────── MACD 趋势过滤【新增】 ───────
    def _is_macd_bullish(self) -> bool:
        """MACD 是否看涨（MACD在线上即可，放松要求，不强制零轴上方）"""
        if not self.p.use_macd_filter:
            return True  # 不启用过滤则直接通过
        # 只要求MACD线上穿信号线，确认趋势方向
        # 不强制要求零轴上方，给新生趋势机会
        return self.macd.macd[0] > self.macd.signal[0]

    # ─────── RSI 条件 ───────
    def _is_rsi_good_long(self) -> bool:
        """RSI 在合理区间（超卖但不超买，适合做多）"""
        return (
            self.rsi[0] >= self.p.rsi_long_low and
            self.rsi[0] <= self.p.rsi_long_max
        )

    def _is_rsi_good_short(self) -> bool:
        """RSI 在合理区间（反弹但未超卖，适合做空）"""
        return (
            self.rsi[0] >= self.p.rsi_short_min and
            self.rsi[0] <= self.p.rsi_short_high
        )

    # ─────── 计算趋势强度 ───────
    def _calc_trend_strength_long(self) -> float:
        """
        计算上涨趋势强度（0-1），用于决定本次建仓的风险比例
        综合三个维度：
        1. 均线偏离度 - SMA10 相对 SMA60 偏离越大，趋势越强
        2. RSI 位置 - RSI 越低位，回调越充分，强度越高
        3. 放量程度 - 成交量相对均线放大越多，强度越高
        """
        # 1. 均线强度：(SMA10 - SMA60) / SMA60
        # 正常范围：0% ~ 15% → 归一化到 0-1
        ma_diff_pct = (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0]
        ma_strength = min(max(ma_diff_pct / 0.15, 0), 1)

        # 2. RSI 强度：RSI 在 [30, 65] 区间，越小越强
        # RSI=30 → 强度1，RSI=65 → 强度0
        rsi_range = self.p.rsi_long_max - self.p.rsi_long_low
        if rsi_range > 0:
            rsi_strength = (self.p.rsi_long_max - self.rsi[0]) / rsi_range
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

    def _calc_trend_strength_short(self) -> float:
        """
        计算下跌趋势强度（0-1），与做多完全对称
        综合三个维度：
        1. 均线偏离度 - SMA10 相对 SMA60 偏离越大（越负），趋势越强
        2. RSI 位置 - RSI 越高位，反弹越充分，强度越高
        3. 放量程度 - 成交量相对均线放大越多，强度越高
        """
        # 1. 均线强度：(SMA60 - SMA10) / SMA60
        # 正常范围：0% ~ 15% → 归一化到 0-1
        ma_diff_pct = (self.sma_long[0] - self.sma_short[0]) / self.sma_long[0]
        ma_strength = min(max(ma_diff_pct / 0.15, 0), 1)

        # 2. RSI 强度：RSI 在 [35, 70] 区间，越大越强
        # RSI=70 → 强度1，RSI=35 → 强度0
        rsi_range = self.p.rsi_short_high - self.p.rsi_short_min
        if rsi_range > 0:
            rsi_strength = (self.rsi[0] - self.p.rsi_short_min) / rsi_range
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
        if self.position_type == 'long':
            # 做多：价格上涨盈利
            return (self.data.close[0] - self.avg_entry_price) / self.avg_entry_price
        else:  # short
            # 做空：价格下跌盈利
            return (self.avg_entry_price - self.data.close[0]) / self.avg_entry_price

    # ─────── 分批止盈逻辑 ───────
    def _check_take_profit(self):
        """检查是否触发分批止盈"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        profit_pct = self._calc_profit_pct()
        current_size = abs(self.position.size)

        # 第一止盈：盈利 15%，平仓 1/3
        if not self.tp_levels['tp1'] and profit_pct >= self.p.tp1_pct:
            close_size = int(current_size * self.p.tp1_ratio)
            if close_size > 0:
                if self.position_type == 'long':
                    self.log(f"第一止盈(多)  盈利={profit_pct:.2%}  卖出={close_size}")
                    self.order = self.sell(size=close_size)
                else:
                    self.log(f"第一止盈(空)  盈利={profit_pct:.2%}  平仓={close_size}")
                    self.order = self.buy(size=close_size)
                self.tp_levels['tp1'] = True

        # 第二止盈：盈利 30%，再平仓 1/3
        elif self.tp_levels['tp1'] and not self.tp_levels['tp2'] and profit_pct >= self.p.tp2_pct:
            close_size = int(current_size * self.p.tp2_ratio)
            if close_size > 0:
                if self.position_type == 'long':
                    self.log(f"第二止盈(多)  盈利={profit_pct:.2%}  卖出={close_size}")
                    self.order = self.sell(size=close_size)
                else:
                    self.log(f"第二止盈(空)  盈利={profit_pct:.2%}  平仓={close_size}")
                    self.order = self.buy(size=close_size)
                self.tp_levels['tp2'] = True

        # 第三止盈：盈利 50% 或趋势反转，清仓
        elif self.tp_levels['tp1'] and self.tp_levels['tp2'] and not self.tp_levels['tp3']:
            trend_ok = self._is_uptrend() if self.position_type == 'long' else self._is_downtrend()
            if profit_pct >= self.p.tp3_pct or not trend_ok:
                self.log(f"第三止盈/趋势反转({self.position_type})  盈利={profit_pct:.2%}  清仓")
                self.close()
                self.tp_levels['tp3'] = True

    # ─────── 更新跟踪止损【新增】 ───────
    def _update_trailing_stop(self):
        """更新跟踪止损：价格创新高则上移止损价"""
        if not self.p.use_trailing_stop or self.position_type != 'long':
            return

        current_price = self.data.close[0]
        if self.highest_price is None or current_price > self.highest_price:
            # 创新高，更新最高价，并上移止损价
            self.highest_price = current_price
            # 新止损价 = 最高价 × (1 - 跟踪回撤比例)
            new_sl = self.highest_price * (1 - self.p.trailing_stop_pct)
            # 只上移，不下移
            if new_sl > self.sl_price:
                self.sl_price = new_sl
                if self.p.verbose:
                    self.log(f"跟踪止损上移  新高={self.highest_price:.2f}  新止损={self.sl_price:.2f}")

    # ─────── 止损逻辑 ───────
    def _check_stop_loss(self):
        """检查止损条件"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        current_price = self.data.close[0]

        # 更新跟踪止损（做多时）
        self._update_trailing_stop()

        if self.position_type == 'long':
            # 做多：价格下跌跌破止损价
            if current_price <= self.sl_price:
                if self.p.use_trailing_stop:
                    self.log(f"触发跟踪止损(多)  price={current_price:.2f}  sl={self.sl_price:.2f}  新高={self.highest_price:.2f}")
                else:
                    self.log(f"触发固定止损(多)  price={current_price:.2f}  sl={self.sl_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
                self.close()
            # 趋势反转止损：SMA10 下穿 SMA30
            elif self.sma_short[0] < self.sma_mid[0]:
                self.log(f"趋势反转止损(多)  SMA10={self.sma_short[0]:.2f}  SMA30={self.sma_mid[0]:.2f}")
                self.close()
        else:  # short
            # 做空：价格上涨涨破止损价
            if current_price >= self.sl_price:
                self.log(f"触发固定止损(空)  price={current_price:.2f}  sl={self.sl_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
                self.close()
            # 趋势反转止损：SMA10 上穿 SMA30
            elif self.sma_short[0] > self.sma_mid[0]:
                self.log(f"趋势反转止损(空)  SMA10={self.sma_short[0]:.2f}  SMA30={self.sma_mid[0]:.2f}")
                self.close()

    # ─────── 入场信号检查 ───────
    def _check_long_signal(self) -> bool:
        """检查做多入场信号"""
        if not self.p.allow_long:
            return False
        # 已有反向仓位，不能同向加仓
        if self.position_type == 'short':
            return False
        # 1. 趋势向上（短、中、长期一致）
        if not self._is_uptrend():
            return False
        # 2. RSI 在合理区间
        if not self._is_rsi_good_long():
            return False
        # 3. 放量确认
        if not self._is_volume_surge():
            return False
        # 4. MACD趋势确认【新增】
        if not self._is_macd_bullish():
            return False
        return True

    def _check_short_signal(self) -> bool:
        """检查做空入场信号"""
        if not self.p.allow_short:
            return False
        # 已有反向仓位，不能同向加仓
        if self.position_type == 'long':
            return False
        # 1. 趋势向下（短、中、长期一致）
        if not self._is_downtrend():
            return False
        # 2. RSI 在合理区间
        if not self._is_rsi_good_short():
            return False
        # 3. 放量确认
        if not self._is_volume_surge():
            return False
        return True

    # ─────── 计算可建仓数量 ───────
    def _calc_available_size(self, is_long: bool) -> int:
        """计算可新增建仓数量（考虑最大仓位限制，基于趋势强度动态调整风险）"""
        portfolio_value = self.broker.getvalue()
        current_shares = abs(self.position.size)
        current_value = current_shares * self.data.close[0]
        max_allowed_value = portfolio_value * self.p.max_position
        available_value = max_allowed_value - current_value

        if available_value <= 0:
            return 0

        # 计算趋势强度（0-1）
        if is_long:
            strength = self._calc_trend_strength_long()
        else:
            strength = self._calc_trend_strength_short()

        # 根据趋势强度计算本次风险比例：base_risk ~ max_risk
        risk_range = self.p.max_risk - self.p.base_risk
        current_risk = self.p.base_risk + strength * risk_range

        # 使用风险计算仓位大小
        # 使用当前价格预估，实际止损会在成交后更新
        est_entry = self.data.close[0]
        risk_amount = portfolio_value * current_risk
        sl_dist = est_entry * self.p.stop_loss_pct  # 止损距离 = 入场价 × 止损比例
        if sl_dist > 0:
            size_from_risk = int(risk_amount / sl_dist)
        else:
            size_from_risk = 0

        # 不能超过可用额度
        size_from_available = int(available_value / est_entry)

        size = min(size_from_risk, size_from_available)

        if self.p.verbose and size > 0:
            side = "多" if is_long else "空"
            self.log(f"趋势强度={strength:.2f}  风险比例={current_risk:.1%}  {side}仓规模={size}")

        return size

    # ─────── 重置状态 ───────
    def _reset_state(self):
        """重置所有状态（清仓后调用）"""
        self.avg_entry_price = 0.0
        self.total_shares = 0
        self.sl_price = None
        self.highest_price = None
        self.position_type = None
        self.tp_levels = {'tp1': False, 'tp2': False, 'tp3': False}

    # ─────── 主逻辑 ───────
    def next(self):
        # 有挂单时不操作
        if self.order:
            return

        # 有持仓时：先检查止损止盈
        if self.position.size != 0:
            self._check_stop_loss()
            self._check_take_profit()

        # 如果已经清仓，重置状态
        if self.position.size == 0:
            if self.avg_entry_price == 0:
                self._reset_state()
            # 不要返回，仍然需要检查新的入场信号

        # 检查做多信号
        long_signal = self._check_long_signal()
        # 检查做空信号
        short_signal = self._check_short_signal()

        if long_signal:
            size = self._calc_available_size(is_long=True)
            if size > 0:
                self.total_shares = abs(self.position.size)
                self.log(
                    f"建多仓  est_price={self.data.close[0]:.2f}  size={size}  "
                    f"RSI={self.rsi[0]:.2f}  "
                    f"SMA10={self.sma_short[0]:.2f}  SMA30={self.sma_mid[0]:.2f}  SMA60={self.sma_long[0]:.2f}"
                )
                self.position_type = 'long'
                self.order = self.buy(size=size)

        elif short_signal:
            size = self._calc_available_size(is_long=False)
            if size > 0:
                self.total_shares = abs(self.position.size)
                self.log(
                    f"建空仓  est_price={self.data.close[0]:.2f}  size={size}  "
                    f"RSI={self.rsi[0]:.2f}  "
                    f"SMA10={self.sma_short[0]:.2f}  SMA30={self.sma_mid[0]:.2f}  SMA60={self.sma_long[0]:.2f}"
                )
                self.position_type = 'short'
                self.order = self.sell(size=size)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if (order.isbuy() and self.position_type == 'long') or (order.issell() and self.position_type == 'short'):
                # 开仓/加仓成交：更新平均建仓成本
                executed_price = order.executed.price
                executed_size = abs(order.executed.size)
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
                if self.position_type == 'long':
                    self.sl_price = self.avg_entry_price * (1 - self.p.stop_loss_pct)
                    # 【新增】初始化跟踪止损最高价
                    if self.p.use_trailing_stop and (self.total_shares - executed_size) == 0:
                        self.highest_price = executed_price
                else:  # short
                    self.sl_price = self.avg_entry_price * (1 + self.p.stop_loss_pct)

                side = "买入" if self.position_type == 'long' else "开空"
                self.log(
                    f"{side}成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"avg_entry={self.avg_entry_price:.2f}  "
                    f"sl={self.sl_price:.2f}  "
                    f"total_shares={self.total_shares}"
                )

            else:
                # 平仓/部分平仓成交
                executed_price = order.executed.price
                executed_size = abs(order.executed.size)
                remaining_shares = self.total_shares - executed_size

                side = "卖出" if self.position_type == 'long' else "平仓"
                self.log(
                    f"{side}成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"remaining_shares={remaining_shares}"
                )

                # 全部平仓后重置状态
                if remaining_shares == 0:
                    self._reset_state()
                else:
                    self.total_shares = remaining_shares

        elif order.status in (order.Canceled, order.Rejected, order.Margin):
            self.log(f"订单失败  status={order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            if trade.value != 0:
                pnl_pct = (trade.pnl / abs(trade.value)) * 100
            else:
                pnl_pct = 0
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
TrendFollowStrategy = MultiPeriodTrendStrategy
