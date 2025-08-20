import pandera as pa
import pandas as pd

OHLCVSchema = pa.DataFrameSchema(
    {
        "open": pa.Column(float, nullable=False, coerce=True),
        "high": pa.Column(float, nullable=False, coerce=True),
        "low": pa.Column(float, nullable=False, coerce=True),
        "close": pa.Column(float, nullable=False, coerce=True),
        "volume": pa.Column(float, nullable=False, coerce=True),
        "symbol": pa.Column(str, nullable=False, coerce=True),
    },
    index=pa.Index(pd.Timestamp, nullable=False, coerce=True),
    strict=True,
    coerce=True,
)

MratZscoreKpiSchema = OHLCVSchema.add_columns(
    {
        "filter_ma": pa.Column(float, nullable=True, coerce=True),
        "mrat": pa.Column(float, nullable=True, coerce=True),
        "mean_mrat": pa.Column(float, nullable=True, coerce=True),
        "stdev_mrat": pa.Column(float, nullable=True, coerce=True),
        "z_score_mrat": pa.Column(float, nullable=True, coerce=True),
    }
)

ListingBackrunKpiSchema = OHLCVSchema.add_columns(
    {
        "volume_usdt_btc_prop": pa.Column(float, nullable=False, coerce=True),
        "btc_vol": pa.Column(float, nullable=False, coerce=True),
        "vol_open_low": pa.Column(float, nullable=False, coerce=True),
        "vol_open_high": pa.Column(float, nullable=False, coerce=True),
    }
)
