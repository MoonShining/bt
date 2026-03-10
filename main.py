import backtrader as bt

def main():
    cerebro = bt.Cerebro()

    # 设置初始资金为 100000.0
    cerebro.broker.setcash(100000.0)
    # 设置交易佣金为千分之三（0.1%）
    cerebro.broker.setcommission(commission=0.001)
    # 滑点 0.1%
    cerebro.broker.set_slippage_perc(0.001)
    
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')


    data = bt.feeds.GenericCSVData(
        dataname="./orcl-1995-2014.txt", dtformat="%Y-%m-%d",
    )
    cerebro.adddata(data)

    cerebro.run()
    cerebro.plot()
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')

if __name__ == '__main__':
    main()