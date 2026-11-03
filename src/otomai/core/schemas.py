import pandas as pd
import pandera.pandas as pa

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
