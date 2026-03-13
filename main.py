import datetime  #For datetime objects
import os.path  # To manage paths
import sys  # To find out the script name (in argv[0])
import backtrader as bt
from qmtdatafeed import test
import backtrader.indicators as btind
import mydatafeed

# 定义RSI趋势策略
class RSIStrategy(bt.Strategy):
    # 策略参数（可回测优化）
    params = (
        ('rsi_period', 5), # RSI计算周期
        ('rsi_low', 45), # RSI超卖阈值
        ('rsi_high', 65), # RSI超买阈值
        ('stop_loss_pct', 0.15), # 止损比例（2%）
        ('take_profit_pct', 0.100)# 止盈比例（4%）
    )

    def __init__(self):
        # 初始化RSI指标
        self.rsi = btind.RSI(self.data, period=self.params.rsi_period)
        
        # 记录订单和止损止盈价格
        self.order = None
        self.stop_loss_price = 0
        self.take_profit_price = 0

    def notify_order(self, order):
        # 订单状态处理（避免重复下单）
        if order.status in [order.Submitted, order.Accepted]:
            return
        self.order = None

    def next(self):
        # 检查是否有足够的数据（至少需要rsi_period + 1天的数据）
        if len(self.data) < self.params.rsi_period + 1:
            return
        
        # 无持仓时判断开仓（使用前一天的数据）
        if not self.position:
            # RSI低于超卖阈值 → 开多仓
            if self.rsi[-1] < self.params.rsi_low:
                # 全仓操作：计算可买入数量（使用前一天的收盘价）
                cash = self.broker.getcash()
                size = int(cash / self.data.close[-1])
                if size > 0:
                    self.order = self.buy(size=size)
                    # 设置止损止盈（基于前一天的收盘价）
                    self.stop_loss_price = self.data.close[-1] * (1 - self.params.stop_loss_pct)
                    self.take_profit_price = self.data.close[-1] * (1 + self.params.take_profit_pct)
        
        # 有持仓时判断止损止盈或RSI超买（使用前一天的数据）
        else:
            # 多头持仓：止损（跌破止损价）或止盈（突破止盈价）或RSI超买
            if self.position.size > 0:
                if (self.data.close[-1] <= self.stop_loss_price or 
                    self.data.close[-1] >= self.take_profit_price or 
                    self.rsi[-1] > self.params.rsi_high):
                    self.close()

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        RSIStrategy
    )

    datapath = './orcl-1995-2014.txt'

    # data = bt.feeds.YahooFinanceCSVData(
    #     dataname=datapath,
    #     fromdate=datetime.datetime(2000, 1, 1),
    #     todate=datetime.datetime(2000, 12, 31),
    #     reverse=False)

    data = mydatafeed.MyData(
        dataname=datapath,
        name='orcl',
        fromdate=datetime.datetime(1995, 1, 3), #注意这里需要和实际数据匹配
        todate=datetime.datetime(1995, 1, 16),
        reverse=False)

    cerebro.adddata(data)
    cerebro.broker.setcash(100000.0)
    # cerebro.addsizer(bt.sizers.FixedSize, stake=10)
    cerebro.broker.setcommission(commission=0.0)

    cerebro.run(maxcpus=1)
    cerebro.plot()
    print(cerebro.broker.getvalue())