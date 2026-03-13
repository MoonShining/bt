from __future__ import (absolute_import, division, print_function, unicode_literals)

from datetime import datetime

from backtrader.feed import DataBase
from backtrader import date2num, TimeFrame


class MyData(DataBase):

    # def __init__(self):
    #     super(MydData, self).__init__()

    #     # 根据 timeframe 判断是日线还是分钟线，设置不同的格式
    #     if self.p.timeframe >= TimeFrame.Days:
    #         self.barsize = 28
    #         self.dtsize = 1
    #         self.barfmt = 'IffffII'   # 日线格式
    #     else:
    #         self.dtsize = 2
    #         self.barsize = 32
    #         self.barfmt = 'IIffffII'  # 分钟线格式

    def start(self):
        self.data = [
            ["1995-01-03","2.179012","2.191358","2.117284","2.117284","1.883304","36301200"],
            ["1995-01-04","2.123457","2.148148","2.092592","2.135803","1.899776","46051600"],
            ["1995-01-05","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-06","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-07","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-08","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-09","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-10","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-11","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-12","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-13","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-14","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-15","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
            ["1995-01-16","2.141975","2.148148","2.086420","2.092592","1.861340","37762800"],
        ]
        self.index = 0
        self.len = len(self.data)

    def _load(self):
        """每次加载一条 bar 数据，核心方法"""
        if self.index >= self.len:
            return False  # 没有文件，结束

        bar = self.data[self.index]
        dt = datetime.strptime(bar[0], "%Y-%m-%d")
        self.lines.datetime[0] = date2num(dt)
        self.lines.open[0] = float(bar[1])
        self.lines.high[0] = float(bar[2])
        self.lines.low[0] = float(bar[3])
        self.lines.close[0] = float(bar[4])
        self.lines.volume[0] = int(bar[6])
        self.lines.openinterest[0] = 0
        self.index += 1
        return True  # 成功加载一条 bar