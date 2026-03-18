"""
Backtrader 回测策略
- 趋势判断：单边上涨 / 震荡行情识别
- 仅在单边上涨趋势做多
- 根据信号强弱动态调整仓位
- 自适应止损（ATR）+ 目标止盈
"""

import backtrader as bt
import backtrader.analyzers as btanalyzers
import numpy as np
import datetime


# ─────────────────────────────────────────────
# 指标：趋势强度综合评分
# ─────────────────────────────────────────────
class TrendStrength(bt.Indicator):
    """
    综合趋势强度指标 (0-100)
    权重：ADX(40%) + EMA斜率(30%) + 价格位置(30%)
    """
    lines = ("score",)
    params = dict(
        adx_period=14,
        ema_fast=20,
        ema_slow=60,
        slope_period=10,
    )

    def __init__(self):
        # ADX 趋势强度
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            period=self.p.adx_period
        )
        # EMA 多空排列
        self.ema_fast = bt.indicators.ExponentialMovingAverage(period=self.p.ema_fast)
        self.ema_slow = bt.indicators.ExponentialMovingAverage(period=self.p.ema_slow)
        # 布林带（判断价格位置）
        self.bb = bt.indicators.BollingerBands(period=20, devfactor=2.0)

    def next(self):
        # 1. ADX 分 (0-40分)：ADX>25 开始有趋势，>40 强趋势
        adx_val = self.adx[0]
        adx_score = min(40, max(0, (adx_val - 15) * 40 / 25))

        # 2. EMA 排列分 (0-30分)：fast>slow 且差距越大越高分
        ema_diff_pct = (self.ema_fast[0] - self.ema_slow[0]) / self.ema_slow[0] * 100
        ema_score = min(30, max(0, ema_diff_pct * 10))

        # 3. 价格位置分 (0-30分)：价格在布林带上轨附近得高分
        bb_range = self.bb.lines.top[0] - self.bb.lines.bot[0]
        if bb_range > 0:
            price_pos = (self.data.close[0] - self.bb.lines.bot[0]) / bb_range
        else:
            price_pos = 0.5
        pos_score = min(30, max(0, price_pos * 30))

        self.lines.score[0] = adx_score + ema_score + pos_score


# ─────────────────────────────────────────────
# 指标：行情类型判断
# ─────────────────────────────────────────────
class MarketRegime(bt.Indicator):
    """
    市场状态识别
    lines.regime: 1=单边上涨, -1=单边下跌, 0=震荡
    """
    lines = ("regime",)
    params = dict(
        adx_period=14,
        adx_threshold=25,       # ADX 高于此值视为趋势行情
        ema_fast=20,
        ema_slow=60,
        lookback=20,            # 用于判断近期高低点
    )

    def __init__(self):
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            period=self.p.adx_period
        )
        self.ema_fast = bt.indicators.ExponentialMovingAverage(period=self.p.ema_fast)
        self.ema_slow = bt.indicators.ExponentialMovingAverage(period=self.p.ema_slow)
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.lookback)
        self.lowest  = bt.indicators.Lowest(self.data.low,  period=self.p.lookback)

    def next(self):
        adx_ok   = self.adx[0] >= self.p.adx_threshold
        bull_ema  = self.ema_fast[0] > self.ema_slow[0]
        # 价格处于近期高位区域 (80% 分位以上)
        rng = self.highest[0] - self.lowest[0]
        if rng > 0:
            pct = (self.data.close[0] - self.lowest[0]) / rng
        else:
            pct = 0.5

        if adx_ok and bull_ema and pct > 0.6:
            self.lines.regime[0] = 1       # 单边上涨
        elif adx_ok and (not bull_ema) and pct < 0.4:
            self.lines.regime[0] = -1      # 单边下跌
        else:
            self.lines.regime[0] = 0       # 震荡


# ─────────────────────────────────────────────
# 主策略
# ─────────────────────────────────────────────
class TrendFollowStrategy(bt.Strategy):
    params = dict(
        # ── 趋势判断 ──
        adx_period=14,
        adx_threshold=25,
        ema_fast=20,
        ema_slow=60,

        # ── 入场信号 ──
        rsi_period=14,
        rsi_oversold=40,        # 回调后RSI低于此值+趋势=入场
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,

        # ── 仓位管理 ──
        base_risk=0.02,         # 基础单笔风险比例 (占总资产)
        max_position=0.95,      # 最大仓位比例
        score_low=40,           # 信号评分低阈值
        score_medium=65,        # 信号评分中阈值

        # ── 止损止盈 ──
        atr_period=14,
        atr_sl_mult=2.0,        # 止损 = 入场价 - N * ATR
        atr_tp_mult=4.0,        # 止盈 = 入场价 + M * ATR
        trail_after_pct=0.03,   # 获利 3% 后转为追踪止损
        trail_atr_mult=1.5,     # 追踪止损距离

        # ── 其他 ──
        verbose=True,
    )

    def __init__(self):
        # ── 趋势 & 行情类型 ──
        self.regime   = MarketRegime(
            adx_period=self.p.adx_period,
            adx_threshold=self.p.adx_threshold,
            ema_fast=self.p.ema_fast,
            ema_slow=self.p.ema_slow,
        )
        self.strength = TrendStrength(
            adx_period=self.p.adx_period,
            ema_fast=self.p.ema_fast,
            ema_slow=self.p.ema_slow,
        )

        # ── 入场辅助 ──
        self.rsi  = bt.indicators.RelativeStrengthIndex(period=self.p.rsi_period)
        self.macd = bt.indicators.MACD(
            period1=self.p.macd_fast,
            period2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.ema_fast = bt.indicators.ExponentialMovingAverage(period=self.p.ema_fast)
        self.ema_slow = bt.indicators.ExponentialMovingAverage(period=self.p.ema_slow)

        # ── 止损 ──
        self.atr = bt.indicators.AverageTrueRange(period=self.p.atr_period)

        # ── 内部状态 ──
        self.order      = None      # 待执行订单
        self.entry_price = None
        self.sl_price    = None
        self.tp_price    = None
        self.trailing    = False    # 是否已切换为追踪止损
        self.trail_price = None

    # ─────── 仓位计算 ───────
    def _calc_size(self, score: float, sl_dist: float) -> int:
        """根据信号评分决定风险比例，再按ATR止损距离计算手数"""
        if score >= self.p.score_medium:
            risk_pct = self.p.base_risk * 1.5   # 强信号：1.5倍风险
        elif score >= self.p.score_low:
            risk_pct = self.p.base_risk          # 中等信号：1倍
        else:
            return 0                              # 弱信号不进场

        portfolio_value = self.broker.getvalue()
        risk_amount     = portfolio_value * risk_pct
        # 每手亏损 = sl_dist（每单位），size = 总风险/每手亏损
        size = int(risk_amount / sl_dist) if sl_dist > 0 else 0

        # 限制最大仓位
        max_size = int(portfolio_value * self.p.max_position / self.data.close[0])
        return min(size, max_size)

    # ─────── 入场信号 ───────
    def _entry_signal(self) -> bool:
        """
        多头入场条件（同时满足）：
        1. 行情为单边上涨
        2. MACD 金叉 或 价格在EMA上方回踩EMA20支撑
        3. RSI 低于超买线（避免追高）
        """
        if self.regime.lines.regime[0] != 1:
            return False

        # MACD 金叉（本K线 macd > signal，上一根 macd <= signal）
        macd_cross = (
            self.macd.lines.macd[0] > self.macd.lines.signal[0]
            and self.macd.lines.macd[-1] <= self.macd.lines.signal[-1]
        )

        # 价格在 EMA20 上方，且 RSI 有回调空间
        ema_support = (
            self.data.close[0] > self.ema_fast[0]
            and self.rsi[0] < 70
        )

        return macd_cross or (ema_support and self.rsi[0] < 60)

    # ─────── 止损/止盈更新 ───────
    def _update_trail(self):
        """持仓中每 bar 检查是否触发止损/止盈/追踪止损"""
        if not self.position:
            return

        price = self.data.close[0]

        # 切换为追踪止损
        if not self.trailing and price >= self.entry_price * (1 + self.p.trail_after_pct):
            self.trailing    = True
            self.trail_price = price - self.atr[0] * self.p.trail_atr_mult
            if self.p.verbose:
                self.log(f">>> 转为追踪止损  trail={self.trail_price:.2f}")

        # 更新追踪止损价（只上移不下移）
        if self.trailing:
            new_trail = price - self.atr[0] * self.p.trail_atr_mult
            if new_trail > self.trail_price:
                self.trail_price = new_trail

        # 判断出场
        active_sl = self.trail_price if self.trailing else self.sl_price

        if price <= active_sl:
            self.log(f"触发止损  price={price:.2f}  sl={active_sl:.2f}")
            self.close()
        elif price >= self.tp_price:
            self.log(f"触发止盈  price={price:.2f}  tp={self.tp_price:.2f}")
            self.close()

    # ─────── 主逻辑 ───────
    def next(self):
        if self.order:          # 有挂单时不操作
            return

        if self.position:
            # 行情转为非上涨趋势时强制平仓
            if self.regime.lines.regime[0] != 1:
                self.log(f"趋势终止平仓  regime={self.regime.lines.regime[0]:.0f}")
                self.close()
                return
            self._update_trail()
            return

        # ── 无持仓：判断入场 ──
        if not self._entry_signal():
            return

        score   = self.strength.lines.score[0]
        atr_val = self.atr[0]
        sl_dist = atr_val * self.p.atr_sl_mult
        size    = self._calc_size(score, sl_dist)

        if size <= 0:
            return

        entry        = self.data.close[0]
        self.sl_price = entry - sl_dist
        self.tp_price = entry + atr_val * self.p.atr_tp_mult
        self.trailing = False
        self.trail_price = None

        self.log(
            f"[BUY]  score={score:.1f}  size={size}"
            f"  entry={entry:.2f}  SL={self.sl_price:.2f}  TP={self.tp_price:.2f}"
        )
        self.order = self.buy(size=size)
        self.entry_price = entry

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"订单成交 BUY  price={order.executed.price:.2f}  cost={order.executed.value:.2f}")
                self.entry_price = order.executed.price
            else:
                self.log(f"订单成交 SELL  price={order.executed.price:.2f}")
                self.entry_price = None
                self.sl_price    = None
                self.tp_price    = None
                self.trailing    = False
        elif order.status in (order.Canceled, order.Rejected, order.Margin):
            self.log(f"订单失败  status={order.status}")
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"平仓盈亏  gross={trade.pnl:.2f}  net={trade.pnlcomm:.2f}")

    def log(self, txt):
        if self.p.verbose:
            dt = self.datas[0].datetime.date(0)
            print(f"[{dt}] {txt}")


# ─────────────────────────────────────────────
# 运行回测
# ─────────────────────────────────────────────
def run_backtest(
    data_path: str = None,
    ticker: str = "SPY",
    fromdate: datetime.date = datetime.date(2020, 1, 1),
    todate:   datetime.date = datetime.date(2024, 12, 31),
    cash: float = 100_000.0,
    commission: float = 0.001,
    use_yfinance: bool = True,
):
    cerebro = bt.Cerebro()

    # ── 数据源 ──
    if data_path:
        data = bt.feeds.GenericCSVData(
            dataname=data_path,
            fromdate=fromdate,
            todate=todate,
            dtformat="%Y-%m-%d",
            datetime=0, open=1, high=2, low=3, close=4, volume=5,
        )
    elif use_yfinance:
        import yfinance as yf
        raw = yf.download(ticker, start=str(fromdate), end=str(todate), auto_adjust=True)
        raw.columns = [c.lower() for c in raw.columns]
        data = bt.feeds.PandasData(dataname=raw, fromdate=fromdate, todate=todate)
    else:
        raise ValueError("请提供 data_path 或设置 use_yfinance=True")

    cerebro.adddata(data)

    # ── 策略 & 账户 ──
    cerebro.addstrategy(TrendFollowStrategy, verbose=True)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.broker.set_slippage_perc(0.001)  # 0.1% 滑点

    # ── 分析器 ──
    cerebro.addanalyzer(btanalyzers.SharpeRatio,    _name="sharpe",   riskfreerate=0.02)
    cerebro.addanalyzer(btanalyzers.DrawDown,        _name="drawdown")
    cerebro.addanalyzer(btanalyzers.TradeAnalyzer,   _name="trades")
    cerebro.addanalyzer(btanalyzers.Returns,         _name="returns")
    cerebro.addanalyzer(btanalyzers.AnnualReturn,    _name="annual")

    # ── 执行 ──
    print(f"\n{'='*55}")
    print(f"  回测品种: {ticker}  {fromdate} → {todate}")
    print(f"  初始资金: {cash:,.0f}")
    print(f"{'='*55}\n")

    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    end_value   = cerebro.broker.getvalue()
    strat       = results[0]

    # ── 结果输出 ──
    print(f"\n{'='*55}")
    print(f"  期末资产   : {end_value:>12,.2f}")
    print(f"  总收益率   : {(end_value/start_value-1)*100:>10.2f}%")

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", None)
    if sharpe is not None:
        print(f"  夏普比率   : {sharpe:>10.3f}")

    dd = strat.analyzers.drawdown.get_analysis()
    print(f"  最大回撤   : {dd.get('max', {}).get('drawdown', 0):>10.2f}%")

    ta = strat.analyzers.trades.get_analysis()
    total  = ta.get("total",  {}).get("total",  0)
    won    = ta.get("won",    {}).get("total",  0)
    lost   = ta.get("lost",   {}).get("total",  0)
    wr     = won / total * 100 if total else 0
    pnl_avg_won  = ta.get("won",  {}).get("pnl", {}).get("average", 0)
    pnl_avg_lost = ta.get("lost", {}).get("pnl", {}).get("average", 0)
    rr = abs(pnl_avg_won / pnl_avg_lost) if pnl_avg_lost else 0
    print(f"  总交易次数 : {total:>10}")
    print(f"  盈利次数   : {won:>10}  ({wr:.1f}%)")
    print(f"  亏损次数   : {lost:>10}")
    print(f"  盈亏比     : {rr:>10.2f}")

    annual = strat.analyzers.annual.get_analysis()
    print("\n  各年度收益:")
    for yr, ret in sorted(annual.items()):
        print(f"    {yr}: {ret*100:+.2f}%")

    print(f"{'='*55}\n")

    # ── 可视化 ──
    try:
        cerebro.plot(style="candlestick", iplot=False, volume=False)
    except Exception as e:
        print(f"绘图失败（可忽略）: {e}")

    return results


# ─────────────────────────────────────────────
if __name__ == "__main__":
    run_backtest(
        ticker="SPY",
        fromdate=datetime.date(2018, 1, 1),
        todate=datetime.date(2024, 12, 31),
        cash=100_000,
        commission=0.001,
        use_yfinance=True,
    )
