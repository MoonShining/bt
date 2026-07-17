import datetime as dt
import os
from typing import Any, Mapping, Optional

import backtrader as bt
import pandas as pd
import requests


DEFAULT_BASE_URL = "https://www.cifangquant.com/api"
DEFAULT_FUND_LIST_ENDPOINT = "/fund/list"
DEFAULT_DAILY_ENDPOINT = "/fund/hist_em"


class CifangQuantPandasData(bt.feeds.PandasData):
    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", "openinterest"),
    )


class CifangQuantClient:
    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        fund_list_endpoint: str = DEFAULT_FUND_LIST_ENDPOINT,
        daily_endpoint: str = DEFAULT_DAILY_ENDPOINT,
        timeout: int = 15,
        session: Optional[Any] = None,
    ):
        self.token = token or os.getenv("CIFANGQUANT_TOKEN")
        self.base_url = (base_url or os.getenv("CIFANGQUANT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.fund_list_endpoint = fund_list_endpoint
        self.daily_endpoint = daily_endpoint
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch_fund_name_map(self, key_word: Optional[str] = None) -> dict[str, str]:
        params = {}
        if key_word:
            params["key_word"] = key_word

        response = self.session.get(
            self._fund_list_url(),
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _extract_fund_name_map(response.json())

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: dt.date,
        end_date: dt.date,
        adjust: Optional[str] = None,
    ) -> pd.DataFrame:
        if not symbol:
            raise ValueError("symbol 不能为空")

        params = {
            "symbol": symbol,
            "start_date": _format_date(start_date),
            "end_date": _format_date(end_date),
            "adjust": adjust or "none",
        }

        response = self.session.get(
            self._daily_url(),
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()

        rows = _extract_rows(response.json(), symbol)
        return normalize_daily_bars(rows)

    def _fund_list_url(self) -> str:
        endpoint = self.fund_list_endpoint
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _daily_url(self) -> str:
        endpoint = self.daily_endpoint
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"x-api-key": self.token}


def create_cifangquant_data(
    symbol: str,
    start_date: dt.date,
    end_date: dt.date,
    token: Optional[str] = None,
    base_url: Optional[str] = None,
    daily_endpoint: str = DEFAULT_DAILY_ENDPOINT,
    adjust: Optional[str] = None,
    session: Optional[Any] = None,
) -> CifangQuantPandasData:
    client = CifangQuantClient(
        token=token,
        base_url=base_url,
        daily_endpoint=daily_endpoint,
        session=session,
    )
    dataframe = client.fetch_daily_bars(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    return CifangQuantPandasData(dataname=dataframe, fromdate=start_date, todate=end_date)


def normalize_daily_bars(rows: list[Any]) -> pd.DataFrame:
    records = []
    for row in rows:
        date_value, open_value, close_value, high_value, low_value, volume_value = _parse_history_row(row)

        records.append(
            {
                "date": _parse_date(date_value),
                "open": _to_float(open_value, "open"),
                "high": _to_float(high_value, "high"),
                "low": _to_float(low_value, "low"),
                "close": _to_float(close_value, "close"),
                "volume": _to_float(volume_value, "volume"),
                "openinterest": 0.0,
            }
        )

    if not records:
        raise ValueError("cifangquant 未返回任何行情数据")

    dataframe = pd.DataFrame.from_records(records)
    dataframe = dataframe.dropna(subset=["date", "open", "high", "low", "close"])
    if dataframe.empty:
        raise ValueError("cifangquant 返回数据缺少有效 OHLC 字段")

    dataframe = dataframe.sort_values("date").drop_duplicates("date", keep="last")
    dataframe = dataframe.set_index(pd.DatetimeIndex(dataframe.pop("date")))
    return dataframe[["open", "high", "low", "close", "volume", "openinterest"]]


def _extract_fund_name_map(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        raise ValueError("cifangquant 基金列表响应不是对象")

    if payload.get("code") not in (None, 0):
        raise ValueError(f"cifangquant 返回错误: {payload.get('message', payload.get('code'))}")

    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("cifangquant 基金列表响应缺少 data 数组")

    names = {}
    for row in data:
        if not isinstance(row, Mapping):
            continue
        code = _pick(row, "fund_code", "code", "symbol")
        name = _pick(row, "fund_name", "name")
        if code and name:
            names[str(code).strip()] = str(name).strip()
    return names


def _extract_rows(payload: Any, symbol: str) -> list[Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("cifangquant 响应不是对象")

    if payload.get("code") not in (None, 0):
        raise ValueError(f"cifangquant 返回错误: {payload.get('message', payload.get('code'))}")

    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("cifangquant 响应缺少 data 对象")

    first_symbol = symbol.split(",", 1)[0].strip()
    rows = data.get(first_symbol)
    if rows is None and len(data) == 1:
        rows = next(iter(data.values()))
    if not isinstance(rows, list):
        raise ValueError(f"cifangquant 响应缺少基金 {first_symbol} 的历史行情")
    return rows


def _parse_history_row(row: Any) -> tuple[Any, Any, Any, Any, Any, Any]:
    if isinstance(row, (list, tuple)):
        if len(row) < 7:
            raise ValueError("cifangquant 历史行情行长度不足 7")
        # 文档格式: [交易日期, 开盘价, 收盘价, 最高价, 最低价, 涨跌幅, 成交量]
        return row[0], row[1], row[2], row[3], row[4], row[6]

    if isinstance(row, Mapping):
        date_value = _pick(row, "date", "trade_date", "datetime", "time")
        open_value = _pick(row, "open", "open_price")
        high_value = _pick(row, "high", "high_price")
        low_value = _pick(row, "low", "low_price")
        close_value = _pick(row, "close", "close_price")
        volume_value = _pick(row, "volume", "vol", "trade_volume", default=0)
        return date_value, open_value, close_value, high_value, low_value, volume_value

    raise ValueError("cifangquant 历史行情行不是数组或对象")


def _pick(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name in row:
            return row[name]
        lowered_name = name.lower()
        if lowered_name in lowered:
            return lowered[lowered_name]
    return default


def _parse_date(value: Any) -> pd.Timestamp:
    if value is None:
        return pd.NaT
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


def _format_date(value: dt.date) -> str:
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.strftime("%Y-%m-%d")


def _to_float(value: Any, field_name: str) -> float:
    if value is None or value == "":
        raise ValueError(f"cifangquant 返回数据缺少 {field_name} 字段")
    return float(value)
