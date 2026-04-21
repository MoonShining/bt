import akshare as ak
import mplfinance as mpf  # Please install mplfinance as follows: pip install mplfinance

# 获取人民币对美元汇率数据
def get_cny_usd_exchange_rate():
    currency_boc_sina_df = ak.currency_boc_sina(symbol="美元", start_date="20230304", end_date="20231110")
    print(currency_boc_sina_df)

# 调用函数获取并打印汇率数据
get_cny_usd_exchange_rate()

# # 获取苹果股票数据
# stock_us_daily_df = ak.stock_us_daily(symbol="AAPL", adjust="qfq")
# stock_us_daily_df = stock_us_daily_df.set_index(["date"])
# stock_us_daily_df = stock_us_daily_df["2020-04-01": "2020-04-29"]
# mpf.plot(stock_us_daily_df, type="candle", mav=(3, 6, 9), volume=True, show_nontrading=False)

