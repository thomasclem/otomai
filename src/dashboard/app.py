
import os
import sys
import asyncio
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine
import yaml
import ccxt
import time

# Add src to path for imports to work
sys.path.append(os.path.abspath("src"))

# Page Config
st.set_page_config(
    page_title="Otomai Dashboard",
    page_icon="📊",
    layout="wide",
)

# --- CUSTOM CSS (Finrax Theme) ---
def load_css():
    st.markdown("""
        <style>
        /* Main Background */
        .stApp {
            background-color: #131722;
            color: #e0e0e0;
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #1e232d;
            border-right: 1px solid #2a2e39;
        }
        
        /* Metrics (Cards) */
        [data-testid="stMetric"] {
            background-color: #1e232d;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            border: 1px solid #2a2e39;
        }
        [data-testid="stMetricLabel"] {
            color: #8b949e;
            font-size: 14px;
        }
        [data-testid="stMetricValue"] {
            color: #2962ff;
            font-weight: 600;
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            background-color: #1e232d;
            color: #e0e0e0;
            border-radius: 8px;
        }
        
        /* Dataframes */
        [data-testid="stDataFrame"] {
            border: 1px solid #2a2e39;
            border-radius: 8px;
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #e0e0e0 !important;
            font-family: 'Inter', sans-serif;
        }
        
        /* Buttons */
        .stButton>button {
            background-color: #2962ff;
            color: white;
            border: none;
            border-radius: 4px;
            font-weight: 600;
        }
        .stButton>button:hover {
            background-color: #1e88e5;
        }
        
        /* Status Colors */
        .status-green { color: #00e676; }
        .status-red { color: #ff1744; }
        
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: #1e232d;
            border-radius: 4px;
            color: #8b949e;
            border: 1px solid #2a2e39;
        }
        .stTabs [aria-selected="true"] {
            background-color: #2962ff !important;
            color: white !important;
        }
        
        </style>
    """, unsafe_allow_html=True)

load_css()

# ==========================================
# HELPER FUNCTIONS
# ==========================================

@st.cache_resource
def get_db_engine():
    db_url = os.getenv("DATABASE_URL", "sqlite:///data/otomai.db")
    if db_url.startswith("sqlite:///data/") and not os.path.exists("data"):
        if os.path.exists("otomai.db"):
             db_url = "sqlite:///otomai.db"
    return create_engine(db_url)


def load_trades(engine) -> pd.DataFrame:
    try:
        query = "SELECT * FROM trade"
        df = pd.read_sql(query, engine)
        if not df.empty:
            df['net_profit'] = pd.to_numeric(df['net_profit'], errors='coerce')
            df['open_price'] = pd.to_numeric(df['open_price'], errors='coerce')
            df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df['open_date'] = pd.to_datetime(df['open_date'])
            df['close_date'] = pd.to_datetime(df['close_date'])
        return df
    except Exception as e:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_btc_ohlcv(timeframe: str = "1d", limit: int = 200) -> pd.DataFrame:
    """Fetch BTC/USDT OHLCV data from Bitget (public, no auth needed)."""
    try:
        exchange = ccxt.bitget({"defaultType": "swap"})
        ohlcv = exchange.fetch_ohlcv("BTC/USDT:USDT", timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as e:
        st.error(f"Failed to fetch BTC data: {e}")
        return pd.DataFrame()


def compute_btc_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Compute BTC regime indicators: SMA 50/200, RSI 14."""
    if df.empty:
        return df
    
    df = df.copy()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["sma_200"] = df["close"].rolling(200).mean()
    
    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # Regime classification
    conditions = [
        (df["sma_50"] > df["sma_200"]) & (df["rsi"] > 50),
        (df["sma_50"] < df["sma_200"]) & (df["rsi"] < 50),
    ]
    choices = ["🟢 Bullish", "🔴 Bearish"]
    df["regime"] = np.select(conditions, choices, default="🟡 Neutral")
    
    return df


def get_running_containers():
    try:
        import docker
        client = docker.from_env()
        containers = client.containers.list()
        strategies = []
        for c in containers:
            try:
                env_vars = c.attrs['Config']['Env']
                env_dict = {k: v for k, v in [e.split('=', 1) for e in env_vars]}
                if 'STRATEGY' in env_dict:
                    strategies.append({
                        "id": c.short_id,
                        "full_id": c.id,
                        "name": c.name,
                        "strategy": env_dict.get('STRATEGY'),
                        "env": env_dict.get('ENV'),
                        "status": c.status
                    })
            except Exception:
                continue
        return strategies
    except Exception:
        return []


def get_container_logs(container_id, lines=100):
    try:
        import docker
        client = docker.from_env()
        container = client.containers.get(container_id)
        return container.logs(tail=lines).decode('utf-8')
    except Exception as e:
        return f"Error fetching logs: {e}"


def fetch_open_positions():
    """Fetch open positions from Bitget (requires auth)."""
    try:
        exchange = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY"),
            "secret": os.getenv("BITGET_SECRET_KEY"),
            "password": os.getenv("BITGET_PASSPHRASE"),
            "defaultType": "swap",
        })
        positions = exchange.fetch_positions()
        # Filter to only active positions (contracts > 0)
        active = [p for p in positions if float(p.get("contracts", 0) or 0) > 0]
        return active, None
    except Exception as e:
        return [], str(e)


def load_config(env, strategy):
    path = f"conf/{env}/{strategy}.yml"
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return None


# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.header("Otomai Dashboard")

# Status Section
st.sidebar.subheader("Live Status")
running_containers = get_running_containers()
selected_container = None

if running_containers:
    container_names = [f"{c['name']} ({c['strategy']})" for c in running_containers]
    selected_container_name = st.sidebar.selectbox("Select Bot to Monitor", container_names)
    for c in running_containers:
        if f"{c['name']} ({c['strategy']})" == selected_container_name:
            selected_container = c
            break
    if selected_container:
        status_color = "green" if selected_container['status'] == 'running' else "red"
        st.sidebar.markdown(f"**Env**: `{selected_container['env']}`")
        st.sidebar.markdown(f"**Status**: :{status_color}[●] {selected_container['status'].upper()}")
else:
    st.sidebar.warning("No running bot detected.")

# Filters
st.sidebar.divider()
st.sidebar.subheader("History Filters")
engine = get_db_engine()
df = load_trades(engine)

all_strategies = df['strategy'].dropna().unique().tolist() if not df.empty else []
selected_strategy_filter = st.sidebar.selectbox(
    "Filter History by Strategy",
    ["All"] + all_strategies
)

# Initial Capital
st.sidebar.divider()
initial_capital = st.sidebar.number_input(
    "Initial Capital ($)", min_value=1.0, value=1000.0, step=100.0,
    help="Used for PnL % and equity curve calculations"
)


# ==========================================
# MAIN PAGE — TABS
# ==========================================

st.title("Trading Performance")

tab_overview, tab_btc, tab_positions, tab_config, tab_logs = st.tabs([
    "📊 Overview", "₿ BTC Regime", "📈 Open Positions", "⚙️ Config", "📋 Logs"
])


# ==========================================
# TAB 1: OVERVIEW (Metrics + Drawdown + History)
# ==========================================

with tab_overview:
    if not df.empty:
        filtered_df = df.copy()
        if selected_strategy_filter != "All":
            filtered_df = filtered_df[filtered_df['strategy'] == selected_strategy_filter]
        filtered_df = filtered_df.sort_values("open_date")

        if not filtered_df.empty:
            # --- METRICS ROW ---
            total_trades = len(filtered_df)
            total_pnl = filtered_df['net_profit'].sum()
            total_pnl_pct = (total_pnl / initial_capital) * 100

            wins = filtered_df[filtered_df['net_profit'] > 0]
            losses = filtered_df[filtered_df['net_profit'] <= 0]
            win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

            avg_win = wins['net_profit'].mean() if len(wins) > 0 else 0
            avg_loss = abs(losses['net_profit'].mean()) if len(losses) > 0 else 0
            win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else float('inf')

            gross_profit = wins['net_profit'].sum() if len(wins) > 0 else 0
            gross_loss = abs(losses['net_profit'].sum()) if len(losses) > 0 else 0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

            avg_return = filtered_df['net_profit'].mean()
            std_return = filtered_df['net_profit'].std()
            sharpe = (avg_return / std_return) if std_return and std_return != 0 else 0

            col1, col2, col3, col4, col5, col6 = st.columns(6)
            col1.metric("Total Trades", total_trades)
            col2.metric("Total PnL", f"${total_pnl:.2f}", delta=f"{total_pnl_pct:+.1f}%")
            col3.metric("Win Rate", f"{win_rate:.1f}%")
            col4.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞")
            col5.metric("Avg Win/Loss", f"{win_loss_ratio:.2f}" if win_loss_ratio != float('inf') else "∞")
            col6.metric("Sharpe", f"{sharpe:.2f}")

            st.markdown("---")

            # --- CHARTS: Equity Curve + Drawdown ---
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.subheader("Equity Curve")
                filtered_df['cumulative_pnl'] = filtered_df['net_profit'].cumsum()
                filtered_df['equity'] = initial_capital + filtered_df['cumulative_pnl']

                fig_equity = go.Figure()
                fig_equity.add_trace(go.Scatter(
                    x=filtered_df['close_date'], y=filtered_df['equity'],
                    mode='lines+markers', name='Equity',
                    line=dict(color='#2962ff', width=2),
                    marker=dict(size=4, color='#00e676'),
                ))
                fig_equity.add_hline(y=initial_capital, line_dash="dash", line_color="#8b949e",
                                     annotation_text="Initial Capital")
                fig_equity.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e0e0e0', title_font_size=16,
                    xaxis=dict(showgrid=True, gridcolor='#2a2e39'),
                    yaxis=dict(showgrid=True, gridcolor='#2a2e39', title="$"),
                    margin=dict(t=30, b=30),
                )
                st.plotly_chart(fig_equity, use_container_width=True)

            with chart_col2:
                st.subheader("Drawdown")
                cumulative = filtered_df['net_profit'].cumsum()
                running_max = cumulative.cummax()
                drawdown = cumulative - running_max
                max_dd = drawdown.min()
                max_dd_pct = (max_dd / initial_capital) * 100 if initial_capital > 0 else 0

                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    x=filtered_df['close_date'], y=drawdown,
                    fill='tozeroy', mode='lines', name='Drawdown',
                    line=dict(color='#ff1744', width=1),
                    fillcolor='rgba(255,23,68,0.2)',
                ))
                fig_dd.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e0e0e0',
                    xaxis=dict(showgrid=True, gridcolor='#2a2e39'),
                    yaxis=dict(showgrid=True, gridcolor='#2a2e39', title="$"),
                    margin=dict(t=30, b=30),
                    annotations=[dict(
                        x=0.5, y=0.95, xref="paper", yref="paper",
                        text=f"Max Drawdown: ${max_dd:.2f} ({max_dd_pct:.1f}%)",
                        showarrow=False, font=dict(size=14, color="#ff1744"),
                    )]
                )
                st.plotly_chart(fig_dd, use_container_width=True)

            st.markdown("---")

            # --- PER-SYMBOL BREAKDOWN ---
            st.subheader("Performance by Symbol")
            symbol_stats = filtered_df.groupby('symbol').agg(
                trades=('net_profit', 'count'),
                total_pnl=('net_profit', 'sum'),
                avg_pnl=('net_profit', 'mean'),
                win_rate=('net_profit', lambda x: (x > 0).sum() / len(x) * 100),
            ).sort_values('total_pnl', ascending=False).reset_index()

            sym_col1, sym_col2 = st.columns(2)

            with sym_col1:
                fig_sym = px.bar(
                    symbol_stats.head(15), x='symbol', y='total_pnl',
                    color='total_pnl',
                    color_continuous_scale=['#ff1744', '#ff1744', '#424242', '#00e676', '#00e676'],
                    title="Top 15 Symbols by PnL",
                )
                fig_sym.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e0e0e0', showlegend=False,
                    xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#2a2e39'),
                    margin=dict(t=40, b=30),
                )
                st.plotly_chart(fig_sym, use_container_width=True)

            with sym_col2:
                st.dataframe(
                    symbol_stats.style.format({
                        'total_pnl': '${:.2f}',
                        'avg_pnl': '${:.2f}',
                        'win_rate': '{:.1f}%',
                    }),
                    use_container_width=True
                )

            st.markdown("---")

            # --- TRADE HISTORY TABLE ---
            with st.expander("📋 Full Trade History", expanded=False):
                display_cols = ['id', 'strategy', 'symbol', 'hold_side', 'open_date', 'close_date',
                                'open_price', 'close_price', 'amount', 'net_profit']
                available_cols = [c for c in display_cols if c in filtered_df.columns]
                st.dataframe(
                    filtered_df[available_cols].sort_values("close_date", ascending=False),
                    use_container_width=True
                )
        else:
            st.info("No trades match the selected filter.")
    else:
        st.info("No historical trades found in database.")


# ==========================================
# TAB 2: BTC REGIME
# ==========================================

with tab_btc:
    st.subheader("Bitcoin Market Regime")

    btc_tf = st.selectbox("BTC Timeframe", ["4h", "1d"], index=1, key="btc_tf")
    btc_limit = st.slider("History (candles)", 100, 500, 200, key="btc_limit")

    btc_df = fetch_btc_ohlcv(timeframe=btc_tf, limit=btc_limit)

    if not btc_df.empty:
        btc_df = compute_btc_regime(btc_df)
        current_regime = btc_df["regime"].iloc[-1] if len(btc_df) > 0 else "N/A"
        current_rsi = btc_df["rsi"].iloc[-1] if len(btc_df) > 0 else 0
        current_price = btc_df["close"].iloc[-1] if len(btc_df) > 0 else 0

        # Regime metrics
        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.metric("Current Regime", current_regime)
        r_col2.metric("BTC Price", f"${current_price:,.0f}")
        r_col3.metric("RSI (14)", f"{current_rsi:.1f}")

        # BTC Price + SMA chart
        fig_btc = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.7, 0.3],
            subplot_titles=("BTC/USDT + Moving Averages", "RSI (14)")
        )

        # Candlestick
        fig_btc.add_trace(go.Candlestick(
            x=btc_df.index,
            open=btc_df['open'], high=btc_df['high'],
            low=btc_df['low'], close=btc_df['close'],
            name='BTC', increasing_line_color='#00e676', decreasing_line_color='#ff1744',
        ), row=1, col=1)

        # SMAs
        fig_btc.add_trace(go.Scatter(
            x=btc_df.index, y=btc_df['sma_50'],
            mode='lines', name='SMA 50',
            line=dict(color='#ffab00', width=1.5),
        ), row=1, col=1)

        fig_btc.add_trace(go.Scatter(
            x=btc_df.index, y=btc_df['sma_200'],
            mode='lines', name='SMA 200',
            line=dict(color='#2962ff', width=1.5),
        ), row=1, col=1)

        # RSI
        fig_btc.add_trace(go.Scatter(
            x=btc_df.index, y=btc_df['rsi'],
            mode='lines', name='RSI',
            line=dict(color='#ab47bc', width=1.5),
        ), row=2, col=1)

        # RSI levels
        fig_btc.add_hline(y=70, line_dash="dash", line_color="#ff1744", row=2, col=1)
        fig_btc.add_hline(y=30, line_dash="dash", line_color="#00e676", row=2, col=1)
        fig_btc.add_hline(y=50, line_dash="dot", line_color="#8b949e", row=2, col=1)

        # Background shading for regime
        for i in range(1, len(btc_df)):
            regime = btc_df['regime'].iloc[i]
            if regime == "🟢 Bullish":
                color = "rgba(0,230,118,0.05)"
            elif regime == "🔴 Bearish":
                color = "rgba(255,23,68,0.05)"
            else:
                continue
            fig_btc.add_vrect(
                x0=btc_df.index[i-1], x1=btc_df.index[i],
                fillcolor=color, layer="below", line_width=0,
                row=1, col=1,
            )

        fig_btc.update_layout(
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            font_color='#e0e0e0', height=700,
            xaxis2=dict(showgrid=True, gridcolor='#2a2e39'),
            yaxis=dict(showgrid=True, gridcolor='#2a2e39'),
            yaxis2=dict(showgrid=True, gridcolor='#2a2e39', range=[0, 100]),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=50, b=30),
        )
        st.plotly_chart(fig_btc, use_container_width=True)

        # Overlay trades on BTC chart if we have them
        if not df.empty:
            st.markdown("---")
            st.subheader("Trades Overlay on BTC Regime")
            st.caption("Shows when trades were opened/closed relative to BTC regime.")

            trades_with_dates = df.dropna(subset=['open_date', 'close_date']).copy()
            if not trades_with_dates.empty:
                fig_overlay = go.Figure()
                fig_overlay.add_trace(go.Scatter(
                    x=btc_df.index, y=btc_df['close'],
                    mode='lines', name='BTC Price',
                    line=dict(color='#8b949e', width=1),
                ))

                # Trade open/close markers
                for _, trade in trades_with_dates.iterrows():
                    color = "#00e676" if trade.get('net_profit', 0) > 0 else "#ff1744"
                    fig_overlay.add_trace(go.Scatter(
                        x=[trade['open_date'], trade['close_date']],
                        y=[None, None],  # y will be interpolated from BTC price
                        mode='markers+text',
                        text=[f"Open {trade['symbol']}", f"Close ${trade.get('net_profit', 0):.2f}"],
                        textposition="top center",
                        marker=dict(size=8, color=color, symbol=['triangle-up', 'triangle-down']),
                        showlegend=False,
                    ))

                fig_overlay.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e0e0e0', height=400,
                    xaxis=dict(showgrid=True, gridcolor='#2a2e39'),
                    yaxis=dict(showgrid=True, gridcolor='#2a2e39', title="BTC Price ($)"),
                    margin=dict(t=30, b=30),
                )
                st.plotly_chart(fig_overlay, use_container_width=True)
    else:
        st.error("Could not fetch BTC data.")


# ==========================================
# TAB 3: OPEN POSITIONS
# ==========================================

with tab_positions:
    st.subheader("Active Positions")

    if st.button("🔄 Refresh Positions"):
        st.cache_data.clear()

    positions, err = fetch_open_positions()

    if err:
        st.error(f"Failed to fetch positions: {err}")
        st.info("Make sure BITGET_API_KEY, BITGET_SECRET_KEY, and BITGET_PASSPHRASE environment variables are set.")
    elif positions:
        st.success(f"Found {len(positions)} active positions.")

        pos_data = []
        for p in positions:
            info = p.get("info", {})
            unrealized_pnl = float(p.get("unrealizedPnl", 0) or 0)
            entry_price = float(p.get("entryPrice", 0) or 0)
            mark_price = float(p.get("markPrice", 0) or 0)
            contracts = float(p.get("contracts", 0) or 0)
            side = p.get("side", "N/A")
            liq_price = float(p.get("liquidationPrice", 0) or 0)
            leverage = p.get("leverage", "N/A")
            pnl_pct = float(info.get("achievedProfits", 0) or 0)

            pos_data.append({
                "Symbol": p.get("symbol", "N/A"),
                "Side": side.upper() if side else "N/A",
                "Size": contracts,
                "Entry Price": f"${entry_price:.4f}",
                "Mark Price": f"${mark_price:.4f}",
                "Liq. Price": f"${liq_price:.4f}" if liq_price else "N/A",
                "Leverage": f"{leverage}x",
                "Unrealized PnL": f"${unrealized_pnl:+.2f}",
                "PnL Color": "🟢" if unrealized_pnl >= 0 else "🔴",
            })

        pos_df = pd.DataFrame(pos_data)
        st.dataframe(pos_df, use_container_width=True, hide_index=True)

        # Total unrealized P&L
        total_upnl = sum(float(p.get("unrealizedPnl", 0) or 0) for p in positions)
        upnl_color = "green" if total_upnl >= 0 else "red"
        st.metric("Total Unrealized PnL", f"${total_upnl:+.2f}")
    else:
        st.info("No active positions.")


# ==========================================
# TAB 4: CONFIG
# ==========================================

with tab_config:
    st.subheader("Configuration")

    conf_col1, conf_col2 = st.columns([1, 2])

    with conf_col1:
        default_env_idx = 0
        conf_envs = ["dev", "preprod", "prod"]
        if selected_container and selected_container.get('env') in conf_envs:
            default_env_idx = conf_envs.index(selected_container['env'])

        env_sel = st.selectbox("Environment", conf_envs, index=default_env_idx)

        import glob
        files = glob.glob(f"conf/{env_sel}/*.yml")
        strategies = [os.path.basename(f).replace(".yml", "") for f in files]

        default_strat_idx = 0
        if selected_container and selected_container.get('strategy') in strategies:
            default_strat_idx = strategies.index(selected_container['strategy'])

        strat_sel = st.selectbox("Strategy Config", strategies, index=default_strat_idx if strategies else 0)

    with conf_col2:
        if strat_sel:
            active_config = load_config(env_sel, strat_sel)
            if active_config:
                st.json(active_config)
            else:
                st.error("Config file not found.")


# ==========================================
# TAB 5: LOGS
# ==========================================

with tab_logs:
    st.subheader("Live Container Logs")

    if selected_container:
        if st.button("🔄 Refresh Logs"):
            pass
        logs = get_container_logs(selected_container['full_id'])
        st.code(logs, language='text')
    else:
        st.info("Select a running bot in the sidebar to view logs.")
