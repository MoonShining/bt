"""
多周期趋势跟随策略
基于 SMA、RSI、成交量的综合判断策略（只做多版本）
- 仅做多，不做空（适合A股指数长期趋势）
- ATR动态止损 + 跟踪止损
- 分批止盈（金字塔式减仓）
- 短、中、长期趋势判断 + 长期趋势过滤
- 支持美债收益率宏观过滤：高收益率环境压缩仓位/禁止开仓
"""

import pandas as pd
import backtrader as bt


class MultiPeriodTrendStrategy(bt.Strategy):
    """
    多周期趋势跟随策略（只做多版本）

    做多入场条件（需同时满足）：
    1. 长期趋势向上：长期均线比N天前抬高
    2. 短、中、长期均线多头排列：SMA20 > SMA60 > SMA120
    3. RSI 回调：RSI(14) 在 25-65 之间（逢低买入）
    4. 放量确认：成交量 > 1.0 × 成交量均线(20)

    风险管理：
    - ATR动态止损：建仓价 - ATR × 倍数
    - 趋势反转止损：需要连续N天跌破均线才确认
    - 跟踪止损：价格创新高自动上移止损位
    - 动态风险：根据趋势强度，每次建仓风险 base_risk% ~ max_risk% 不等

    分批止盈：
    - 盈利 > 15% → 卖出 1/3
    - 盈利 > 30% → 再卖出 1/3
    - 盈利 > 50% **或**触发止损/趋势反转 → 清仓剩余
    """

    params = dict(
        # ── 均线指标（短期、中期、长期）──
        sma_short=20,         # 短期均线
        sma_mid=60,           # 中期均线
        sma_long=120,         # 长期均线

        # ── RSI 指标 ──
        rsi_period=14,
        rsi_long_low=25,     # RSI 低于此值不入场，超卖区域才入场
        rsi_long_max=65,     # RSI 高于此值不入场（避免追高）

        # ── 成交量指标 ──
        vol_ma_period=20,     # 成交量均线周期
        vol_multiplier=1.0,   # 放量要求

        # ── ATR 动态止损 ──
        use_atr_stop=True,    # 使用ATR动态止损
        atr_period=14,        # ATR计算周期
        atr_multiplier=3.0,   # 止损宽度 = ATR × 倍数

        # ── 固定止损（ATR停用备用）──
        stop_loss_pct=0.08,   # 固定止损比例

        # ── 趋势反转止损优化 ──
        trend_reversal_bars=3,  # 需要连续N天跌破才触发趋势反转止损
                               # 避免假突破误止损

        # ── 加仓限制 ──
        min_bars_between_add=8,  # 两次加仓之间最小间隔N个交易日
                                # 避免同一趋势上过度加仓

        # ── 跟踪止损 ──
        use_trailing_stop=True,  # 启用跟踪止损，让利润奔跑
        trailing_stop_pct=0.15,  # 跟踪止损回撤比例（从最高点回撤）

        # ── 分批止盈 ──
        tp1_pct=0.15,         # 第一止盈位
        tp1_ratio=0.33,       # 第一止盈卖出比例
        tp2_pct=0.30,         # 第二止盈位
        tp2_ratio=0.33,       # 第二止盈卖出比例
        tp3_pct=0.50,         # 第三止盈位（盈利达到清仓）

        # ── 长期趋势过滤 ──
        require_long_uptrend=True,  # 只在长期趋势向上时做多
        long_trend_lookback=100,    # 检查长期均线在N天前位置

        # ── 仓位管理：基于趋势强度的动态风险 ──
        base_risk=0.10,      # 最小风险比例
        max_risk=0.40,       # 最大风险比例
        max_position=0.95,   # 总最大仓位（占总资金比例）
        max_single_position=0.95,  # 单票最大仓位

        # ── 美债收益率宏观过滤 ──
        enable_us10y_filter=False,  # 是否启用美债收益率过滤
        us10y_high_threshold=4.5,   # 高收益率阈值（%），超过此值禁止开新仓
        us10y_low_threshold=3.0,    # 低收益率阈值（%），低于此值流动性宽松
        us10y_data_path="./us10y_daily.csv",  # 美债数据文件路径

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

        # ── ATR 波动率指标 ──
        if self.p.use_atr_stop:
            self.atr = bt.indicators.AverageTrueRange(
                self.data,
                period=self.p.atr_period
            )

        # ── 美债收益率数据加载 ──
        self.us10y_df = None
        if self.p.enable_us10y_filter:
            try:
                import pandas as pd
                import os
                if os.path.exists(self.p.us10y_data_path):
                    self.us10y_df = pd.read_csv(self.p.us10y_data_path)
                    self.us10y_df['date'] = pd.to_datetime(self.us10y_df['date']).dt.date
                    if self.p.verbose:
                        print(f"[美债过滤] 已加载 {len(self.us10y_df)} 条美债收益率数据")
                else:
                    print(f"[美债过滤] 警告：数据文件 {self.p.us10y_data_path} 不存在，美债过滤不生效")
            except Exception as e:
                print(f"[美债过滤] 加载数据失败：{e}，美债过滤不生效")

        # ── 内部状态 ──
        self.order = None
        self.avg_entry_price = 0.0    # 平均建仓价格
        self.total_shares = 0         # 累计持仓股数
        self.sl_price = None          # 止损价
        self.highest_price = None     # 持仓以来最高价，用于跟踪止损
        self.last_add_bar = None      # 上次加仓所在bar索引，控制加仓间隔
        self.down_bars_count = 0      # 连续跌破均线天数，用于趋势反转止损延迟
        self.position_type = 'long'   # 只做多，固定为long
        self.tp_levels = {
            'tp1': False,
            'tp2': False,
            'tp3': False,
        }

    # ─────── 趋势判断 ───────
    def _is_uptrend(self) -> bool:
        """判断短、中、长期趋势一致向上（多头排列）"""
        return (
            self.sma_short[0] > self.sma_mid[0] and    # 短期 > 中期
            self.sma_mid[0] > self.sma_long[0]         # 中期 > 长期
        )

    def _is_long_term_uptrend(self) -> bool:
        """检查长期趋势是否整体向上（长期均线比N天前抬高）"""
        if not self.p.require_long_uptrend:
            return True  # 不要求则直接通过
        # 需要足够多的历史数据才能判断
        if len(self) < self.p.long_trend_lookback:
            return False  # 数据不足，不入场
        # 比较当前长期均线和N天前的长期均线
        long_ago_sma = self.sma_long[-self.p.long_trend_lookback]
        current_sma = self.sma_long[0]
        # 长期均线向上抬高 → 长期趋势向上
        return current_sma > long_ago_sma

    # ─────── 放量判断 ───────
    def _is_volume_surge(self) -> bool:
        """判断是否满足放量条件"""
        if self.vol_ma[0] > 0:
            return self.data.volume[0] > self.vol_ma[0] * self.p.vol_multiplier
        return False

    # ─────── 检查趋势反转条件 ───────
    def _check_trend_reversal(self) -> bool:
        """
        检查是否真的趋势反转
        需要连续N天SMA短 < SMA中才确认，避免假突破
        """
        is_current_down = self.sma_short[0] < self.sma_mid[0]

        if is_current_down:
            self.down_bars_count += 1
        else:
            self.down_bars_count = 0  # 重置计数

        # 连续N天跌破才确认反转
        return self.down_bars_count >= self.p.trend_reversal_bars

    # ─────── RSI 条件 ───────
    def _is_rsi_good_long(self) -> bool:
        """RSI 在合理区间（超卖但不超买，适合做多）"""
        return (
            self.rsi[0] >= self.p.rsi_long_low and
            self.rsi[0] <= self.p.rsi_long_max
        )

    # ─────── 计算趋势强度 ───────
    def _calc_trend_strength_long(self) -> float:
        """
        计算上涨趋势强度（0-1），用于决定本次建仓的风险比例
        综合三个维度：
        1. 均线偏离度 - SMA短 相对 SMA长 偏离越大，趋势越强
        2. RSI 位置 - RSI 越低位，回调越充分，强度越高
        3. 放量程度 - 成交量相对均线放大越多，强度越高
        """
        # 1. 均线强度：(SMA短 - SMA长) / SMA长
        # 正常范围：0% ~ 15% → 归一化到 0-1
        ma_diff_pct = (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0]
        ma_strength = min(max(ma_diff_pct / 0.15, 0), 1)

        # 2. RSI 强度：RSI 在 [low, max] 区间，越小越强
        # RSI=low → 强度1，RSI=max → 强度0
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

    # ─────── 计算当前盈利比例 ───────
    def _calc_profit_pct(self) -> float:
        """计算当前持仓盈利比例（基于平均建仓成本）"""
        if self.avg_entry_price == 0:
            return 0
        # 做多：价格上涨盈利
        return (self.data.close[0] - self.avg_entry_price) / self.avg_entry_price

    # ─────── 更新跟踪止损 ───────
    def _update_trailing_stop(self):
        """更新跟踪止损：价格创新高则上移止损价"""
        if not self.p.use_trailing_stop:
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

    # ─────── 分批止盈逻辑 ───────
    def _check_take_profit(self):
        """检查是否触发分批止盈"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        profit_pct = self._calc_profit_pct()
        current_size = abs(self.position.size)

        # 第一止盈：盈利达到 tp1_pct，平仓 tp1_ratio
        if not self.tp_levels['tp1'] and profit_pct >= self.p.tp1_pct:
            close_size = int(current_size * self.p.tp1_ratio)
            if close_size > 0:
                self.log(f"第一止盈(多)  盈利={profit_pct:.2%}  卖出={close_size}")
                self.order = self.sell(size=close_size)
                self.tp_levels['tp1'] = True
            return

        # 第二止盈：盈利达到 tp2_pct，再平仓 tp2_ratio
        if self.tp_levels['tp1'] and not self.tp_levels['tp2'] and profit_pct >= self.p.tp2_pct:
            close_size = int(current_size * self.p.tp2_ratio)
            if close_size > 0:
                self.log(f"第二止盈(多)  盈利={profit_pct:.2%}  卖出={close_size}")
                self.order = self.sell(size=close_size)
                self.tp_levels['tp2'] = True
            return

        # 第三止盈：盈利达到 tp3_pct 或 趋势反转 → 清仓剩余
        if self.tp_levels['tp1'] and self.tp_levels['tp2'] and not self.tp_levels['tp3']:
            trend_ok = self._is_uptrend()
            if profit_pct >= self.p.tp3_pct or not trend_ok:
                self.log(f"第三止盈/趋势反转(多)  盈利={profit_pct:.2%}  清仓")
                self.order = self.close()
                self.tp_levels['tp3'] = True

    # ─────── 止损逻辑 ───────
    def _check_stop_loss(self):
        """检查止损条件"""
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        current_price = self.data.close[0]

        # 更新跟踪止损
        self._update_trailing_stop()

        # 做多：价格下跌跌破止损价
        if current_price <= self.sl_price:
            if self.p.use_trailing_stop:
                self.log(f"触发跟踪止损(多)  price={current_price:.2f}  sl={self.sl_price:.2f}  新高={self.highest_price:.2f}")
            else:
                self.log(f"触发固定止损(多)  price={current_price:.2f}  sl={self.sl_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
            self.close()
            return

        # 趋势反转止损：SMA短 下穿 SMA中
        elif self._check_trend_reversal():
            self.log(f"趋势反转止损(多)  连续{self.p.trend_reversal_bars}天跌破  SMA{self.p.sma_short}={self.sma_short[0]:.2f}  SMA{self.p.sma_mid}={self.sma_mid[0]:.2f}")
            self.close()
            return

    # ─────── 入场信号检查 ───────
    # ─────── 美债收益率宏观过滤 ───────
    def _get_current_us10y(self) -> float:
        """获取当前日期的美债收益率"""
        if self.us10y_df is None or self.us10y_df.empty:
            return float('nan')

        current_date = self.data.datetime.date(0)

        # 查找 exact match
        match = self.us10y_df[self.us10y_df['date'] == current_date]
        if not match.empty:
            return match.iloc[0]['us10y']

        # 找不到，找日期之前的最后一个数据
        prev = self.us10y_df[self.us10y_df['date'] < current_date]
        if not prev.empty:
            return prev.iloc[-1]['us10y']

        return float('nan')

    def _is_us10y_allowed(self) -> bool:
        """检查美债收益率是否允许开仓
        仅在2020年以后应用美债过滤，之前不添加
        """
        if not self.p.enable_us10y_filter or self.us10y_df is None:
            return True  # 不启用则直接通过

        current_date = self.data.datetime.date(0)
        # 仅在2020年以后应用美债过滤
        if current_date.year < 2020:
            return True

        current_yield = self._get_current_us10y()

        if pd.isna(current_yield):
            # 找不到数据，保守处理，允许开仓但警告
            if self.p.verbose:
                self.log(f"[美债过滤] 找不到当前日期收益率数据，默认允许开仓")
            return True

        # 收益率超过高阈值，禁止开新仓
        if current_yield >= self.p.us10y_high_threshold:
            if self.p.verbose:
                self.log(f"[美债过滤] {current_date}: 美债收益率 {current_yield:.2f}% 超过阈值 {self.p.us10y_high_threshold}%，禁止开新仓")
            return False

        return True

    def _calc_us10y_risk_scale(self) -> float:
        """根据美债收益率计算风险仓位调整系数

        逻辑：
        - 收益率 <= low_threshold → 流动性宽松 → 系数 1.0（不压缩）
        - 收益率 >= high_threshold → 流动性紧张 → 已经禁止开仓，系数 0
        - 中间区域 → 线性压缩
        - 仅在2020年以后应用美债调整，之前不压缩
        """
        if not self.p.enable_us10y_filter or self.us10y_df is None:
            return 1.0

        current_date = self.data.datetime.date(0)
        # 仅在2020年以后应用美债仓位压缩
        if current_date.year < 2020:
            return 1.0

        current_yield = self._get_current_us10y()
        if pd.isna(current_yield):
            return 1.0

        if current_yield <= self.p.us10y_low_threshold:
            # 低收益率，流动性宽松，不压缩仓位
            return 1.0
        elif current_yield >= self.p.us10y_high_threshold:
            # 高收益率，已经禁止开仓
            return 0.0
        else:
            # 中间区间，线性压缩仓位
            # yield: low → high   →  scale: 1.0 → 0.0
            range_pct = (current_yield - self.p.us10y_low_threshold) / (self.p.us10y_high_threshold - self.p.us10y_low_threshold)
            scale = 1.0 - range_pct
            return scale

    def _check_long_signal(self) -> bool:
        """检查做多入场信号"""
        # 如果已经加仓到最大单票仓位，不再加仓
        portfolio_value = self.broker.getvalue()
        current_value = abs(self.position.size) * self.data.close[0]
        max_single_value = portfolio_value * self.p.max_single_position
        if current_value >= max_single_value:
            return False

        # 加仓间隔限制
        if self.position.size != 0 and self.last_add_bar is not None:
            bars_since_last_add = len(self) - self.last_add_bar
            if bars_since_last_add < self.p.min_bars_between_add:
                # 间隔不够，不允许加仓
                return False

        # 1. 长期趋势过滤：只在长期向上趋势中做多
        if not self._is_long_term_uptrend():
            return False
        # 2. 趋势向上（短、中、长期多头排列）
        if not self._is_uptrend():
            return False
        # 3. RSI 在合理区间（回调确认，避免追高）
        if not self._is_rsi_good_long():
            return False
        # 4. 放量确认（验证突破有效性）
        if not self._is_volume_surge():
            return False
        # 5. 美债收益率宏观过滤（如果启用）
        if not self._is_us10y_allowed():
            return False

        return True

    # ─────── 计算可建仓数量 ───────
    def _calc_available_size(self) -> int:
        """计算可新增建仓数量（考虑最大仓位限制，基于趋势强度动态调整风险）"""
        portfolio_value = self.broker.getvalue()
        current_shares = abs(self.position.size)
        current_value = current_shares * self.data.close[0]
        max_allowed_value = portfolio_value * self.p.max_position
        available_value = max_allowed_value - current_value

        if available_value <= 0:
            return 0

        # 加仓间隔限制已经在信号检查做过了

        # 计算趋势强度（0-1）
        strength = self._calc_trend_strength_long()

        # 根据趋势强度计算本次风险比例：base_risk ~ max_risk
        risk_range = self.p.max_risk - self.p.base_risk
        current_risk = self.p.base_risk + strength * risk_range

        # 美债收益率动态调整风险仓位
        # 高收益率环境压缩仓位，低收益率不压缩
        us10y_scale = self._calc_us10y_risk_scale()
        if us10y_scale < 1.0 and self.p.verbose:
            current_yield = self._get_current_us10y()
            self.log(f"[美债调整] 收益率={current_yield:.2f}%  仓位压缩系数={us10y_scale:.2f}")
        current_risk = current_risk * us10y_scale

        if current_risk <= 0:
            return 0

        # 使用风险计算仓位大小
        # 止损距离根据是否用ATR而不同
        est_entry = self.data.close[0]
        risk_amount = portfolio_value * current_risk

        if self.p.use_atr_stop:
            # ATR止损：风险金额 = 仓位 × ATR × 倍数
            # => 仓位 = 风险金额 / (ATR × 倍数)
            atr_value = self.atr[0]
            sl_dist = self.p.atr_multiplier * atr_value
        else:
            # 固定百分比止损
            sl_dist = est_entry * self.p.stop_loss_pct  # 止损距离 = 入场价 × 止损比例

        if sl_dist > 0:
            size_from_risk = int(risk_amount / sl_dist)
        else:
            size_from_risk = 0

        # 不能超过可用额度
        size_from_available = int(available_value / est_entry)

        # 不能超过单票剩余空间
        max_single_value = portfolio_value * self.p.max_single_position
        remaining_single = max_single_value - current_value
        size_from_single = int(remaining_single / est_entry)

        size = min(size_from_risk, size_from_available, size_from_single)

        if self.p.verbose and size > 0:
            current_yield = self._get_current_us10y()
            if not pd.isna(current_yield) and self.p.enable_us10y_filter:
                self.log(f"趋势强度={strength:.2f}  美债={current_yield:.2f}%  风险比例={current_risk:.1%}  多仓规模={size}")
            else:
                self.log(f"趋势强度={strength:.2f}  风险比例={current_risk:.1%}  多仓规模={size}")

        return max(size, 0)

    # ─────── 重置状态 ───────
    def _reset_state(self):
        """重置所有状态（清仓后调用）"""
        self.avg_entry_price = 0.0
        self.total_shares = 0
        self.sl_price = None
        self.highest_price = None
        self.last_add_bar = None
        self.down_bars_count = 0
        self.position_type = 'long'
        self.tp_levels = {'tp1': False, 'tp2': False, 'tp3': False}

    # ─────── 主逻辑 ───────
    def next(self):
        # 有挂单时不操作
        if self.order:
            return

        # 有持仓时：先检查止损止盈
        if self.position.size != 0:
            self._check_stop_loss()
            if not self.order:  # 止损没触发，检查止盈
                self._check_take_profit()
            if self.order:
                # 已经下单退出，返回
                return

        # 如果已经清仓，重置状态
        if self.position.size == 0:
            if self.avg_entry_price != 0:
                self._reset_state()
            # 不要返回，仍然需要检查新的入场信号

        # 检查做多信号
        long_signal = self._check_long_signal()
        if long_signal:
            size = self._calc_available_size()
            if size > 0:
                self.total_shares = abs(self.position.size)
                self.log(
                    f"建多仓  est_price={self.data.close[0]:.2f}  size={size}  "
                    f"RSI={self.rsi[0]:.2f}  "
                    f"SMA{self.p.sma_short}={self.sma_short[0]:.2f}  "
                    f"SMA{self.p.sma_mid}={self.sma_mid[0]:.2f}  "
                    f"SMA{self.p.sma_long}={self.sma_long[0]:.2f}"
                )
                self.position_type = 'long'
                self.order = self.buy(size=size)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order.isbuy() and self.position_type == 'long':
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
                # 记录本次加仓的bar索引，用于控制加仓间隔
                self.last_add_bar = len(self)

                # 更新止损价（基于最新平均成本）
                if self.p.use_atr_stop:
                    # ATR动态止损：止损 = 入场价 - ATR × 倍数
                    atr_value = self.atr[0]
                    self.sl_price = executed_price - self.p.atr_multiplier * atr_value
                else:
                    # 固定百分比止损
                    self.sl_price = self.avg_entry_price * (1 - self.p.stop_loss_pct)
                # 初始化跟踪止损最高价
                if self.p.use_trailing_stop and old_shares == 0:
                    self.highest_price = executed_price

                self.log(
                    f"买入成交  price={executed_price:.2f}  "
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

                self.log(
                    f"卖出成交  price={executed_price:.2f}  "
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
            import datetime as dt_module
            current_date = dt_module.date.today()
            if dt == current_date:
                # 当前日期，红色显示
                print(f"\033[91m[{dt}] {txt}\033[0m")
            else:
                print(f"[{dt}] {txt}")


# 兼容旧的策略类名
TrendFollowStrategy = MultiPeriodTrendStrategy
