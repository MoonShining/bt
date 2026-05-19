"""
均值回归策略 (Mean Reversion Strategy)
基于布林带 (Bollinger Bands) 实现的经典均值回归策略
改进版本：支持分批止盈、动态仓位管理、多次加仓

核心理念：
价格总是围绕其均值波动，当价格大幅偏离均线时，预期会向均值回归。
- 价格跌破下轨 → 超卖，买入做多
- 价格涨破上轨 → 超买，卖出做空
- 盈利达到目标位后分批止盈，让利润奔跑
"""

import backtrader as bt


class MeanReversionStrategy(bt.Strategy):
    """
    基于布林带的均值回归策略（改进版）

    策略逻辑：
    1. 使用布林带衡量价格偏离程度
       - 中轨：移动平均线
       - 上轨：中轨 + N × 标准差
       - 下轨：中轨 - N × 标准差

    2. 入场条件：
       - 做多：价格从下向上穿越下轨（价格从超卖区域回归）
       - 做空：价格从上向下穿越上轨（价格从超买区域回归）
       - 支持多次加仓：只要还有仓位空间且满足信号即可加仓

    3. 分批止盈：
       - 第一止盈：盈利 > 10% → 卖出 1/3
       - 第二止盈：盈利 > 20% → 再卖出 1/3
       - 第三止盈：盈利 > 30% 或 价格回到中轨 或 趋势反转 → 清仓剩余

    4. 止损：
       - 固定比例止损：建仓后下跌一定比例立即止损
       - 反向穿越止损：价格反向突破布林带中轨确认趋势改变，清仓止损
    """

    params = dict(
        # ── 布林带参数 ──
        bb_period=20,          # 布林带周期（均线周期）
        bb_dev=2.0,            # 布林带标准差倍数（2.0倍，只在大幅偏离才入场，减少假信号）

        # ── 入场过滤 ──
        crossover_only=True,         # 只在穿越时入场（避免持续在外反复开仓）
        min_bars_between_add=8,      # 两次加仓之间更大间隔，减少过度交易

        # ── 分批止盈设置 ──
        enable_scaled_tp=True,       # 启用分批止盈
        tp1_pct=0.12,                # 第一止盈位：盈利 12%（更高门槛，让利润跑）
        tp1_ratio=0.33,              # 第一止盈卖出比例
        tp2_pct=0.25,                # 第二止盈位：盈利 25%
        tp2_ratio=0.33,              # 第二止盈卖出比例
        tp3_pct=0.40,                # 第三止盈位：盈利 40%
        exit_on_middle_band=False,   # 价格回到中轨不强制清仓，让利润奔跑

        # ── 止损设置 ──
        stop_loss_pct=0.10,          # 固定止损比例（10%，给价格更多波动空间）
        stop_on_reverse_cross=True,  # 反向穿越布林带中线止损（趋势反转）

        # ── 仓位管理：基于偏离度的动态仓位 ──
        base_risk=0.05,              # 最小风险比例
        max_risk=0.12,               # 最大风险比例
        max_position=0.80,           # 总最大仓位（占总资金比例）
        max_single_position=0.40,    # 单票最大仓位（避免单票过重）

        # ── 双向交易开关 ──
        allow_short=False,           # 关闭做空（ORCL长期上涨趋势，做空亏损严重）
        allow_long=True,             # 是否允许做多

        # ── 其他 ──
        verbose=True,
    )

    def __init__(self):
        # 计算布林带
        self.bollinger = bt.indicators.BollingerBands(
            self.data.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_dev
        )
        self.mid = self.bollinger.lines.mid    # 中轨（均线）
        self.top = self.bollinger.lines.top    # 上轨
        self.bot = self.bollinger.lines.bot    # 下轨

        # 穿越检测器
        # 价格上穿下轨 → 做多信号
        self.cross_buy = bt.indicators.CrossOver(self.data.close, self.bot)
        # 价格下穿上轨 → 做空信号
        self.cross_sell = bt.indicators.CrossOver(self.top, self.data.close)
        # 价格上穿中轨检测
        self.cross_above_mid = bt.indicators.CrossOver(self.data.close, self.mid)
        # 价格下穿中轨检测
        self.cross_below_mid = bt.indicators.CrossOver(self.mid, self.data.close)

        # 内部状态
        self.order = None
        self.avg_entry_price = 0.0    # 平均建仓价格
        self.total_shares = 0         # 累计持仓股数（绝对值）
        self.stop_loss_price = 0.0    # 止损价
        self.last_add_bar = None      # 上次加仓所在bar索引，控制加仓间隔
        self.position_type = None     # 'long' / 'short' / None
        # 分批止盈状态记录
        self.tp_levels = {
            'tp1': False,
            'tp2': False,
            'tp3': False,
        }

    # ─────── 计算偏离度（信号强度）───────
    def _calc_deviation_pct(self, is_long: bool) -> float:
        """
        计算价格偏离布林带的程度，偏离越大信号越强
        做多：价格在 下轨 下方，偏离越大（越负）越强
        做空：价格在 上轨 上方，偏离越大（越正）越强

        注意：当 crossover_only=True，当前bar已经完成穿越，价格已经在轨道内了
        需要用上一根bar的价格（仍在轨道外）来计算偏离度
        """
        # 使用上一根bar计算偏离，因为当前bar已经穿越完成价格在内侧
        price = self.data.close[-1]
        bot = self.bot[-1]
        top = self.top[-1]
        mid = self.mid[-1]

        if is_long:
            # 做多：偏离度 = (下轨 - 价格) / 中轨 → 价格越低于下轨，偏离越大
            deviation = (bot - price) / mid
        else:
            # 做空：偏离度 = (价格 - 上轨) / 中轨 → 价格越高于上轨，偏离越大
            deviation = (price - top) / mid

        # 如果上一根也没偏离，给个最小强度
        if deviation <= 0:
            return 0.0

        # 归一化到 [0, 1]：偏离 0% → 强度 0，偏离 5% → 强度 1
        strength = min(max(deviation / 0.05, 0), 1)
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

    # ─────── 检查做多信号 ───────
    def _is_long_signal(self) -> bool:
        """检查做多信号"""
        if not self.p.allow_long:
            return False

        if self.position_type == 'short':
            return False  # 已有空仓，不做多

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
                return False

        # 信号1：价格上穿下轨（从下方向上穿越）
        # 穿越前价格在下轨下方，穿越后到上方 → 此时收盘价可能已经在上方，但确认曾偏离到外侧
        if self.p.crossover_only:
            has_crossover = self.cross_buy[0] > 0
            # 穿越即说明曾在外侧，无需额外检查
            return has_crossover
        else:
            # 不要求穿越，只要价格现在在外侧即可
            has_signal = self.data.close[0] < self.bot[0]
            return has_signal

    # ─────── 检查做空信号 ───────
    def _is_short_signal(self) -> bool:
        """检查做空信号"""
        if not self.p.allow_short:
            return False

        if self.position_type == 'long':
            return False  # 已有多仓，不做空

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
                return False

        # 信号1：价格下穿上轨（从上向下穿越）
        # 穿越前价格在上轨上方，穿越后到下方 → 穿越即说明曾偏离到外侧
        if self.p.crossover_only:
            has_crossover = self.cross_sell[0] > 0
            # 穿越即说明曾在外侧，无需额外检查
            return has_crossover
        else:
            # 不要求穿越，只要价格现在在外侧即可
            has_signal = self.data.close[0] > self.top[0]
            return has_signal

    # ─────── 分批止盈检查 ───────
    def _check_scaled_take_profit(self):
        """检查分批止盈"""
        if not self.p.enable_scaled_tp:
            return
        if self.avg_entry_price == 0 or self.position.size == 0:
            return

        profit_pct = self._calc_profit_pct()
        current_size = abs(self.position.size)

        # 第一止盈：盈利达到 tp1_pct，平仓 tp1_ratio
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
            return

        # 第二止盈：盈利达到 tp2_pct，再平仓 tp2_ratio
        if self.tp_levels['tp1'] and not self.tp_levels['tp2'] and profit_pct >= self.p.tp2_pct:
            close_size = int(current_size * self.p.tp2_ratio)
            if close_size > 0:
                if self.position_type == 'long':
                    self.log(f"第二止盈(多)  盈利={profit_pct:.2%}  卖出={close_size}")
                    self.order = self.sell(size=close_size)
                else:
                    self.log(f"第二止盈(空)  盈利={profit_pct:.2%}  平仓={close_size}")
                    self.order = self.buy(size=close_size)
                self.tp_levels['tp2'] = True
            return

        # 第三止盈：盈利达到 tp3_pct OR 价格回到中轨 → 清仓剩余
        if self.tp_levels['tp1'] and self.tp_levels['tp2'] and not self.tp_levels['tp3']:
            trigger_tp3 = False
            if profit_pct >= self.p.tp3_pct:
                trigger_tp3 = True
            elif self.p.exit_on_middle_band:
                # 做多：价格回到/突破中轨 → 止盈
                if self.position_type == 'long' and (self.cross_above_mid[0] > 0 or self.data.close[0] >= self.mid[0]):
                    trigger_tp3 = True
                # 做空：价格回到/跌破中轨 → 止盈
                elif self.position_type == 'short' and (self.cross_below_mid[0] > 0 or self.data.close[0] <= self.mid[0]):
                    trigger_tp3 = True

            if trigger_tp3:
                self.log(f"第三止盈/清仓({self.position_type})  盈利={profit_pct:.2%}")
                self.order = self.close()
                self.tp_levels['tp3'] = True
            return

    # ─────── 检查止损/止盈退出 ───────
    def _check_exit_full(self) -> bool:
        """
        检查是否需要全额退出（未触发分批止盈时的全额退出检查）
        返回 True 表示需要全额清仓
        """
        current_price = self.data.close[0]

        # 1. 固定止损
        if self.p.stop_loss_pct is not None:
            if self.position_type == 'long' and current_price <= self.stop_loss_price:
                self.log(f"多头触发固定止损  price={current_price:.2f}  stop={self.stop_loss_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
                return True
            if self.position_type == 'short' and current_price >= self.stop_loss_price:
                self.log(f"空头触发固定止损  price={current_price:.2f}  stop={self.stop_loss_price:.2f}  avg_entry={self.avg_entry_price:.2f}")
                return True

        # 2. 趋势反转止损：反向穿越中轨
        if self.p.stop_on_reverse_cross:
            if self.position_type == 'long':
                # 多头：价格跌破中轨 → 趋势向下，清仓
                if self.cross_below_mid[0] > 0 or current_price < self.mid[0]:
                    self.log(f"多头趋势反转  price跌破中轨  price={current_price:.2f}  mid={self.mid[0]:.2f}")
                    return True
            if self.position_type == 'short':
                # 空头：价格涨破中轨 → 趋势向上，清仓
                if self.cross_above_mid[0] > 0 or current_price > self.mid[0]:
                    self.log(f"空头趋势反转  price涨破中轨  price={current_price:.2f}  mid={self.mid[0]:.2f}")
                    return True

        # 3. 不启用分批止盈时，如果价格回到中轨就全额止盈
        if not self.p.enable_scaled_tp and self.p.exit_on_middle_band:
            if self.position_type == 'long' and (self.cross_above_mid[0] > 0 or current_price >= self.mid[0]):
                self.log(f"多头到达中轨止盈  price={current_price:.2f}  mid={self.mid[0]:.2f}")
                return True
            if self.position_type == 'short' and (self.cross_below_mid[0] > 0 or current_price <= self.mid[0]):
                self.log(f"空头到达中轨止盈  price={current_price:.2f}  mid={self.mid[0]:.2f}")
                return True

        return False

    # ─────── 计算可建仓数量 ───────
    def _calc_available_size(self, is_long: bool) -> int:
        """计算可新增建仓数量（基于偏离度动态调整仓位）"""
        portfolio_value = self.broker.getvalue()
        current_shares = abs(self.position.size)
        current_value = current_shares * self.data.close[0]
        max_allowed_value = portfolio_value * self.p.max_position
        available_value = max_allowed_value - current_value

        if available_value <= 0:
            return 0

        # 计算信号强度（基于偏离度）
        strength = self._calc_deviation_pct(is_long)

        # 根据信号强度计算本次风险比例：base_risk ~ max_risk
        risk_range = self.p.max_risk - self.p.base_risk
        current_risk = self.p.base_risk + strength * risk_range

        # 使用风险计算仓位大小
        # 止损距离 = 入场价 × 止损比例
        est_entry = self.data.close[0]
        risk_amount = portfolio_value * current_risk
        sl_dist = est_entry * self.p.stop_loss_pct

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
            side = "多" if is_long else "空"
            self.log(f"偏离强度={strength:.2f}  风险比例={current_risk:.1%}  {side}仓规模={size}")

        return max(size, 0)

    # ─────── 重置状态 ───────
    def _reset_state(self):
        """重置所有状态（清仓后调用）"""
        self.avg_entry_price = 0.0
        self.total_shares = 0
        self.stop_loss_price = 0.0
        self.last_add_bar = None
        self.position_type = None
        self.tp_levels = {'tp1': False, 'tp2': False, 'tp3': False}

    # ─────── 主逻辑 ───────
    def next(self):
        # 有挂单时不操作
        if self.order:
            return

        # 有持仓时：先检查退出条件
        if self.position.size != 0:
            # 先检查是否需要全额止损退出
            if self._check_exit_full():
                self.log(f"{self.position_type}清仓（止损/全止盈）")
                self.order = self.close()
                self._reset_state()
                return
            # 再检查分批止盈（部分退出）
            self._check_scaled_take_profit()
            if self.order:
                # 分批止盈已经下单，返回
                return

        # 如果已经清仓，重置状态
        if self.position.size == 0:
            if self.avg_entry_price != 0:
                self._reset_state()

        # 检查做多信号
        if self._is_long_signal():
            size = self._calc_available_size(is_long=True)
            if size > 0:
                self.total_shares = abs(self.position.size)
                self.log(
                    f"建多仓  price={self.data.close[0]:.2f}  size={size}  "
                    f"bot={self.bot[0]:.2f}  mid={self.mid[0]:.2f}  top={self.top[0]:.2f}"
                )
                self.position_type = 'long'
                self.order = self.buy(size=size)

        # 检查做空信号
        elif self._is_short_signal():
            size = self._calc_available_size(is_long=False)
            if size > 0:
                self.total_shares = abs(self.position.size)
                self.log(
                    f"建空仓  price={self.data.close[0]:.2f}  size={size}  "
                    f"bot={self.bot[0]:.2f}  mid={self.mid[0]:.2f}  top={self.top[0]:.2f}"
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
                    # 加仓：加权平均
                    self.avg_entry_price = (
                        (self.avg_entry_price * old_shares) + (executed_price * executed_size)
                    ) / new_shares

                self.total_shares = new_shares
                # 记录本次加仓的bar索引，用于控制加仓间隔
                self.last_add_bar = len(self)

                # 更新止损价（基于最新平均成本）
                if self.position_type == 'long':
                    self.stop_loss_price = self.avg_entry_price * (1 - self.p.stop_loss_pct)
                else:  # short
                    self.stop_loss_price = self.avg_entry_price * (1 + self.p.stop_loss_pct)

                side = "买入" if self.position_type == 'long' else "开空"
                self.log(
                    f"{side}成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"avg_entry={self.avg_entry_price:.2f}  "
                    f"stop_loss={self.stop_loss_price:.2f}  "
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
