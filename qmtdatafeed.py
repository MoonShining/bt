import backtrader as bt
import datetime
import pandas as pd
from typing import Optional, List, Dict

# QMT 环境依赖（需在 QMT 终端内运行，或配置 QMT 本地 SDK 环境）
# from xtquant import xtdata
# from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback


# class QMTDataFeed(bt.feed.DataBase):
#     """
#     基于讯投 QMT API 的 backtrader 数据feed
#     支持：历史数据回测（get_market_data_ex）、实时行情推送（subscribe_quote）
#     兼容周期：tick/1m/5m/15m/30m/60m/1d/1w/1mon 等 QMT 支持的所有周期
#     """
#     params = (
#         # 基础配置
#         ("stock_code", "000001.SZ"),  # 标的代码（格式：stkcode.market）
#         ("period", "1d"),             # 数据周期（参考 QMT period 枚举）
#         ("dividend_type", "front"),   # 复权方式：none/front/back/front_ratio/back_ratio
#         # 历史数据配置
#         ("start_date", ""),           # 起始时间（格式：20230101 或 20230101093000）
#         ("end_date", ""),             # 结束时间（空字符串表示最新）
#         ("fill_data", True),          # 是否填充停牌数据
#         # 实时行情配置
#         ("is_realtime", False),       # 是否启用实时推送（实盘模式）
#         ("callback", None),           # 实时数据回调函数（可选）
#     )

#     def __init__(self):
#         super().__init__()
#         # 初始化 QMT 客户端
#         self.xt_trader = XtQuantTrader(r"QMT 安装路径\userdata_mini", session_id="backtrader_feed")
#         self.callback = XtQuantTraderCallback()
#         self.xt_trader.register_callback(self.callback)
        
#         # 数据缓存与状态
#         self.data_buffer: List[Dict] = []  # 存储解析后的行情数据
#         self.current_idx = 0               # 当前读取索引
#         self.sub_id: Optional[int] = None  # 实时订阅ID（实盘模式）

#     def start(self):
#         """启动数据feed：连接QMT + 加载历史数据/订阅实时行情"""
#         # 1. 连接 QMT 客户端
#         connect_result = self.xt_trader.connect()
#         if not connect_result.success:
#             raise ConnectionError(f"QMT 连接失败：{connect_result.message}")

#         # 2. 区分回测（历史数据）与实盘（实时推送）
#         if self.p.is_realtime:
#             # 实盘模式：订阅实时行情
#             self._subscribe_realtime_data()
#         else:
#             # 回测模式：下载历史数据（可选增量下载）
#             self._download_history_data()
#             # 读取并解析历史数据
#             self._load_history_data()

#     def stop(self):
#         """停止数据feed：断开QMT + 取消实时订阅"""
#         if self.p.is_realtime and self.sub_id:
#             # 取消实时订阅
#             self.xt_trader.unsubscribe_quote(self.sub_id)
#         # 断开 QMT 连接
#         self.xt_trader.disconnect()

#     def _download_history_data(self):
#         """调用 QMT download_history_data 下载历史数据（确保本地数据完整）"""
#         # 仅下载 QMT 基础周期（合成周期无需单独下载，QMT 自动合成）
#         base_periods = ["tick", "1m", "5m", "1d"]
#         download_period = self.p.period if self.p.period in base_periods else "5m"
        
#         self.xt_trader.download_history_data(
#             stockcode=self.p.stock_code,
#             period=download_period,
#             startTime=self.p.start_date,
#             endTime=self.p.end_date,
#             incrementally=True  # 增量下载（仅下载新增数据）
#         )

#     def _load_history_data(self):
#         """调用 QMT get_market_data_ex 读取历史数据并解析"""
#         # 调用 QMT API 获取数据
#         result = self.xt_trader.get_market_data_ex(
#             fields=["open", "high", "low", "close", "volume", "amount", "time"],
#             stock_code=[self.p.stock_code],
#             period=self.p.period,
#             start_time=self.p.start_date,
#             end_time=self.p.end_date,
#             dividend_type=self.p.dividend_type,
#             fill_data=self.p.fill_data,
#             subscribe=False  # 仅读取历史数据，不订阅实时更新
#         )

#         # 校验数据是否获取成功
#         if self.p.stock_code not in result:
#             raise ValueError(f"未获取到 {self.p.stock_code} 的历史数据（周期：{self.p.period}）")
        
#         # 解析 DataFrame 为 backtrader 兼容格式
#         df = result[self.p.stock_code]
#         if df.empty:
#             raise ValueError("获取的历史数据为空")

#         # 转换时间格式（QMT time 字段为毫秒时间戳，转 datetime）
#         df["datetime"] = pd.to_datetime(df["time"], unit="ms")
        
#         # 过滤停牌数据（如果设置 fill_data=False）
#         if not self.p.fill_data:
#             df = df[df["suspendFlag"] == 0]  # suspendFlag=0 表示未停牌

#         # 数据排序（按时间升序）
#         df = df.sort_values("datetime").reset_index(drop=True)

#         # 存入数据缓存（映射 backtrader 字段）
#         for _, row in df.iterrows():
#             self.data_buffer.append({
#                 "datetime": row["datetime"],
#                 "open": row["open"],
#                 "high": row["high"],
#                 "low": row["low"],
#                 "close": row["close"],
#                 "volume": row["volume"],
#                 "openinterest": 0,  # 股票无持仓量，默认填0
#             })

#     def _subscribe_realtime_data(self):
#         """调用 QMT subscribe_quote 订阅实时行情（实盘模式）"""
#         # 注册实时数据回调（用于接收推送）
#         self.callback.on_disconnected = self._on_disconnected
#         self.callback.on_quote = self._on_realtime_quote

#         # 发起订阅
#         subscribe_result = self.xt_trader.subscribe_quote(
#             stockcode=self.p.stock_code,
#             period=self.p.period,
#             dividend_type=self.p.dividend_type,
#             result_type="DataFrame",  # 返回格式：DataFrame/dict/list
#             callback=self.p.callback or self._default_realtime_callback
#         )

#         if not subscribe_result.success:
#             raise RuntimeError(f"实时行情订阅失败：{subscribe_result.message}")
#         self.sub_id = subscribe_result.data  # 保存订阅ID，用于后续取消订阅

#     def _on_realtime_quote(self, data: Dict):
#         """实时行情推送回调：接收QMT推送并加入数据缓存"""
#         if self.p.stock_code not in data:
#             return
        
#         # 解析推送数据（与历史数据格式对齐）
#         realtime_df = data[self.p.stock_code]
#         for _, row in realtime_df.iterrows():
#             self.data_buffer.append({
#                 "datetime": pd.to_datetime(row["time"], unit="ms"),
#                 "open": row["open"],
#                 "high": row["high"],
#                 "low": row["low"],
#                 "close": row["close"],
#                 "volume": row["volume"],
#                 "openinterest": 0,
#             })

#     def _default_realtime_callback(self, data: Dict):
#         """默认实时数据回调（打印日志）"""
#         print(f"实时数据推送 - {self.p.stock_code}：{data}")

#     def _on_disconnected(self):
#         """QMT 断开连接回调"""
#         raise ConnectionError("QMT 连接断开，实时行情推送停止")

#     def _load(self):
#         """backtrader 核心方法：读取下一条数据并填充到feed"""
#         # 检查是否有未读取的数据
#         if self.current_idx >= len(self.data_buffer):
#             # 实时模式下等待新数据，回测模式返回False表示数据结束
#             if self.p.is_realtime:
#                 return False  # backtrader 会循环调用，直到有新数据
#             return False

#         # 获取当前数据
#         current_data = self.data_buffer[self.current_idx]

#         # 填充 backtrader 标准字段
#         self.lines.datetime[0] = bt.date2num(current_data["datetime"])
#         self.lines.open[0] = current_data["open"]
#         self.lines.high[0] = current_data["high"]
#         self.lines.low[0] = current_data["low"]
#         self.lines.close[0] = current_data["close"]
#         self.lines.volume[0] = current_data["volume"]
#         self.lines.openinterest[0] = current_data["openinterest"]

#         # 索引递增
#         self.current_idx += 1
#         return True


def test():
    # ------------------------------
    # 使用示例（回测 + 实盘）
    # ------------------------------
    print("this is test")