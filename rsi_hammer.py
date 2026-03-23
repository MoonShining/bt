import backtrader as bt
import pandas as pd
import datetime

# 核心策略类：下跌趋势RSI+底部形态共振做多
class BottomReversalStrategy(bt.Strategy):
    # 策略参数（可外部优化）
    params = (
        ('printlog', True),          # 是否打印日志
        ('rsi_period', 14),          # RSI周期
        ('rsi_oversold', 40),        # RSI超卖阈值
        ('atr_period', 14),          # ATR周期
        ('atr_stop_mult', 2.0),      # ATR止损倍数
        ('ma_short', 5),             # 短期均线
        ('ma_long', 20),             # 长期均线
        ('down_trend_pct', 5),       # 下跌趋势跌幅阈值（%）
        ('down_trend_days', 10),     # 下跌趋势计算天数
    )

    def __init__(self):
        # 1. 基础数据引用
        self.open = self.data.open
        self.high = self.data.high
        self.low = self.data.low
        self.close = self.data.close
        self.volume = self.data.volume

        # 2. 趋势判断指标
        self.ma_short = bt.indicators.SimpleMovingAverage(self.close, period=self.p.ma_short)
        self.ma_long = bt.indicators.SimpleMovingAverage(self.close, period=self.p.ma_long)
        # 近N日跌幅（用于判定下跌趋势）
        self.close_10d_ago = self.close(-self.p.down_trend_days)
        self.down_trend_pct = (self.close / self.close_10d_ago - 1) * 100

        # 3. 超卖指标：RSI
        self.rsi = bt.indicators.RelativeStrengthIndex(
            self.close, period=self.p.rsi_period
        )

        # 4. 底部反转形态（锤子线+早晨之星）
        self.hammer = bt.talib.CDLHAMMER(self.open, self.high, self.low, self.close)
        self.morning_star = bt.talib.CDLMORNINGSTAR(self.open, self.high, self.low, self.close)

        # 5. ATR指标（用于止损）
        self.atr = bt.indicators.AverageTrueRange(period=self.p.atr_period)

        # 6. 持仓相关变量
        self.buy_price = 0.0    # 买入价格
        self.stop_price = 0.0   # 止损价格
        self.in_position = False # 是否持仓

    def next(self):
        # 跳过数据预热阶段
        if len(self) < max(self.p.atr_period, self.p.rsi_period, self.p.down_trend_days):
            return

        # --------------- 步骤1：判定是否为下跌趋势 ---------------
        is_down_trend = (
            self.ma_short[0] < self.ma_long[0]  # 5日均线 < 20日均线
            and self.down_trend_pct[0] < -self.p.down_trend_pct  # 近10日跌幅≥5%
        )

        # --------------- 步骤2：识别底部反转形态+RSI超卖共振 ---------------
        is_bottom_pattern = (self.hammer[0] == 100) or (self.morning_star[0] == 100)
        is_rsi_oversold = self.rsi[0] < self.p.rsi_oversold
        buy_signal = is_down_trend and is_bottom_pattern and is_rsi_oversold and not self.in_position

        # --------------- 步骤3：买入做多 ---------------
        if buy_signal:
            # 市价买入
            self.buy(exectype=bt.Order.Market)
            # 记录买入价格和计算ATR止损价
            self.buy_price = self.close[0]
            self.stop_price = self.buy_price - self.atr[0] * self.p.atr_stop_mult
            self.in_position = True
            self.log(f"买入 | 价格：{self.buy_price:.2f}，ATR止损价：{self.stop_price:.2f}")

        # --------------- 步骤4：ATR止损 ---------------
        if self.in_position and self.close[0] < self.stop_price:
            self.close()  # 止损平仓
            self.in_position = False
            self.log(f"止损卖出 | 价格：{self.close[0]:.2f}，止损价：{self.stop_price:.2f}")

        # --------------- 步骤5：上升趋势结束卖出（无止损时） ---------------
        if self.in_position:
            # 上升趋势结束判定：5日均线死叉20日均线，或收盘价跌破5日均线且成交量放大
            is_ma_death_cross = (self.ma_short[0] < self.ma_long[0]) and (self.ma_short[-1] >= self.ma_long[-1])
            is_break_ma5 = (self.close[0] < self.ma_short[0]) and (self.volume[0] > self.volume[-1] * 1.2)
            sell_signal = is_ma_death_cross or is_break_ma5

            if sell_signal:
                self.close()
                self.in_position = False
                self.log(f"趋势结束卖出 | 价格：{self.close[0]:.2f}，买入价：{self.buy_price:.2f}")

    def notify_order(self, order):
        # 订单状态通知（可选）
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"买入成交 | 价格：{order.executed.price:.2f}")
            elif order.issell():
                self.log(f"卖出成交 | 价格：{order.executed.price:.2f}")

    def log(self, txt):
        """日志打印函数"""
        if self.p.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} - {txt}")

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(BottomReversalStrategy)

    datapath1 = './orcl-1995-2014.txt'
    data1 = bt.feeds.YahooFinanceCSVData(
        dataname=datapath1,
        fromdate=datetime.datetime(1995, 1, 1),
        todate=datetime.datetime(2000, 12, 31),
        reverse=False)
    cerebro.adddata(data1, name='ORCL')

    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    cerebro.run(maxcpus=1)
    cerebro.plot(style='candlestick')
    print(cerebro.broker.getvalue())