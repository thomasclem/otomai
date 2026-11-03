import pandas as pd
import ta


class MRAT:
    def __init__(self, slow_ma_length: int, fast_ma_length: int, values: pd.Series):
        if slow_ma_length <= fast_ma_length:
            raise ValueError("slow_ma_length must be greater than fast_ma_length")

        if values.empty:
            raise ValueError("The input series is empty")

        self.slow_ma_length = slow_ma_length
        self.fast_ma_length = fast_ma_length
        self.values = values

        self._fast_ma_series = ta.trend.sma_indicator(close=self.values, window=self.fast_ma_length)
        self._slow_ma_series = ta.trend.sma_indicator(close=self.values, window=self.slow_ma_length)

    def calculate_mrat(self) -> pd.Series:
        return self._fast_ma_series / self._slow_ma_series
