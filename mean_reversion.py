"""
均值回归策略 - 基于布林带
适合长江电力这种基本面稳定的公用事业股

策略逻辑：
1. 使用布林带判断价格偏离程度
2. 价格跌破布林带下轨 → 超卖，回归均值预期 → 买入
3. 价格涨破布林带上轨 → 超买，回归均值预期 → 卖出
4. 仓位管理：分档建仓，偏离越大仓位越重
"""

import backtrader as bt
import pandas as pd


class BollingerMeanReversionStrategy(bt.Strategy):
    """
    布林带均值回归策略

    适合：基本面稳定、股价围绕均值波动的股票
    如：长江电力、高速公路、公用事业等高股息稳定股
    """

    params = dict(
        # ── 布林带参数 ──
        bb_period=20,          # 布林带周期
        bb_dev=2.0,           # 标准差倍数

        # ── 建仓规则 ──
        max_position=0.95,    # 最大仓位
        position_scale=True,  # 是否按偏离程度分级建仓
        # 偏离越大，仓位越重：
        # - 偏离 1σ → 建仓 1/3
        # - 偏离 1.5σ → 建仓 2/3
        # - 偏离 2σ → 满仓

        # ── 止损止盈 ──
        stop_loss_pct=0.20,   # 最大止损比例（最优参数）
        take_profit_pct=None, # None 表示让布林带自动止盈，不固定止盈

        # ── 美债收益率宏观过滤 ──
        enable_us10y_filter=False,  # 是否启用美债收益率过滤
        us10y_high_threshold=4.5,   # 高收益率阈值（%），超过此值禁止开新仓
        us10y_low_threshold=3.0,    # 低收益率阈值（%），低于此值流动性宽松
        us10y_data_path="./us10y_daily.csv",  # 美债数据文件路径

        # ── 其他 ──
        verbose=True,
    )

    def __init__(self):
        # 布林带指标
        self.bb = bt.indicators.BollingerBands(
            self.data.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_dev)

        # ── 美债收益率数据加载 ──
        self.us10y_df = None
        if self.p.enable_us10y_filter:
            try:
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

        # 内部状态
        self.order = None
        self.avg_entry_price = 0.0
        self.total_shares = 0
        self.sl_price = None

    # ────── 美债收益率相关方法 ──────
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
            # 找不到数据，保守处理，允许开仓
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

    def _calc_target_position(self) -> float:
        """根据偏离程度计算目标仓位"""
        if not self.p.position_scale:
            # 不分级，直接满仓
            return self.p.max_position

        # 当前价格相对于中轨的偏离
        price = self.data.close[0]
        mid = self.bb.mid[0]
        std = self.bb.top[0] - mid  # 一个标准差的距离

        deviation = (mid - price) / std  # 偏离中轨多少个标准差，向下偏离为正

        if deviation <= 0:
            # 价格在中轨上方，不开仓
            return 0.0
        elif deviation <= 1.0:
            # 偏离不到1σ，轻仓
            return self.p.max_position * 0.33
        elif deviation <= 1.5:
            # 偏离1-1.5σ，半仓
            return self.p.max_position * 0.67
        else:
            # 偏离超过1.5σ，满仓
            return self.p.max_position

    def next(self):
        # 有挂单不操作
        if self.order:
            return

        portfolio_value = self.broker.getvalue()
        current_value = self.position.size * self.data.close[0]
        current_pct = current_value / portfolio_value

        price = self.data.close[0]

        # ── 检查止损 ──
        if self.position.size > 0 and self.sl_price is not None:
            if price <= self.sl_price:
                self.log(f"触发止损  price={price:.2f}  sl={self.sl_price:.2f}")
                self.order = self.close()
                return

        # ── 美债高收益率主动减仓 ──
        if self.position.size > 0 and self.p.enable_us10y_filter:
            current_date = self.data.datetime.date(0)
            if current_date.year >= 2020:
                current_yield = self._get_current_us10y()
                if not pd.isna(current_yield) and current_yield >= self.p.us10y_high_threshold:
                    # 美债收益率过高 → 主动卖出一半降低风险
                    sell_size = int(self.position.size * 0.5)
                    if sell_size > 0:
                        self.log(f"[美债减仓] {current_date}: 美债收益率={current_yield:.2f}% > {self.p.us10y_high_threshold}%，卖出 {sell_size}")
                        self.order = self.sell(size=sell_size)
                        return

        # ── 布林带均值回归信号 ──
        # 价格跌破下轨 → 超卖 → 买入
        if price < self.bb.bot[0]:

            # 美债宏观过滤（如果启用）
            if not self._is_us10y_allowed():
                return

            target_pct = self._calc_target_position()
            if target_pct <= 0:
                return

            # 美债收益率动态仓位压缩
            us10y_scale = self._calc_us10y_risk_scale()
            if us10y_scale <= 0:
                return
            target_pct = target_pct * us10y_scale

            target_value = portfolio_value * target_pct
            current_value = abs(self.position.size) * price
            available_value = target_value - current_value

            if available_value <= price:  # 不够买1股
                return

            if current_pct >= self.p.max_position:
                return

            size = int(available_value / price)
            if size > 0:
                deviation = (self.bb.mid[0] - price) / (self.bb.top[0] - self.bb.mid[0])
                self.log(
                    f"买入  price={price:.2f}  "
                    f"偏离={deviation:.2f}σ  "
                    f"目标仓位={target_pct:.1%}  size={size}"
                )
                self.order = self.buy(size=size)
                return

        # 价格涨破上轨 → 超买 → 卖出
        elif price > self.bb.top[0] and self.position.size > 0:
            self.log(f"卖出  price={price:.2f}  价格突破上轨")
            self.order = self.close()
            return

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order.isbuy():
                executed_price = order.executed.price
                executed_size = abs(order.executed.size)
                old_shares = self.total_shares
                new_shares = old_shares + executed_size

                if old_shares == 0:
                    self.avg_entry_price = executed_price
                else:
                    self.avg_entry_price = (
                        (self.avg_entry_price * old_shares) + (executed_price * executed_size)
                    ) / new_shares

                self.total_shares = new_shares

                # 设置止损
                if self.p.stop_loss_pct > 0:
                    self.sl_price = self.avg_entry_price * (1 - self.p.stop_loss_pct)

                self.log(
                    f"买入成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"avg_entry={self.avg_entry_price:.2f}  "
                    f"sl={self.sl_price:.2f}"
                )

            else:
                executed_price = order.executed.price
                executed_size = abs(order.executed.size)
                remaining_shares = self.total_shares - executed_size

                self.log(
                    f"卖出成交  price={executed_price:.2f}  "
                    f"size={executed_size}  "
                    f"remaining={remaining_shares}"
                )

                if remaining_shares == 0:
                    self.avg_entry_price = 0.0
                    self.total_shares = 0
                    self.sl_price = None
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
