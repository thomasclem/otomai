
import os
import sys
import asyncio
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
import yaml
import docker

# Add src to path for imports to work
sys.path.append(os.path.abspath("src"))

from otomai.services.exchange import BitgetExchange

# Page Config
st.set_page_config(
    page_title="Otomai Dashboard",
    page_icon="📊",
    layout="wide",
)

# --- HELPER FUNCTIONS ---

@st.cache_resource
def get_db_engine():
    db_url = os.getenv("DATABASE_URL", "sqlite:///data/otomai.db")
    if db_url.startswith("sqlite:///data/") and not os.path.exists("data"):
        if os.path.exists("otomai.db"):
             db_url = "sqlite:///otomai.db"
    return create_engine(db_url)

def load_trades(engine):
    try:
        query = "SELECT * FROM trade"
        df = pd.read_sql(query, engine)
        if not df.empty:
            df['net_profit'] = pd.to_numeric(df['net_profit'], errors='coerce')
            df['open_date'] = pd.to_datetime(df['open_date'])
            df['close_date'] = pd.to_datetime(df['close_date'])
        return df
    except Exception as e:
        # st.error(f"Error loading trades: {e}")
        return pd.DataFrame()

def get_running_containers():
    try:
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
    except Exception as e:
        return []

def get_container_logs(container_id, lines=100):
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
        return container.logs(tail=lines).decode('utf-8')
    except Exception as e:
        return f"Error fetching logs: {e}"

async def fetch_live_orders_async(symbol):
    exchange = BitgetExchange()
    try:
        if not exchange.is_authenticated():
            return None, "Exchange not authenticated (API Keys missing in environment)"
        
        # fetch_open_orders might require symbol
        orders = await exchange.session.fetch_open_orders(symbol)
        await exchange.close_session()
        return orders, None
    except Exception as e:
        await exchange.close_session()
        return None, str(e)

def get_live_orders(symbol):
    try:
        return asyncio.run(fetch_live_orders_async(symbol))
    except Exception as e:
        return None, str(e)

def load_config(env, strategy):
    path = f"conf/{env}/{strategy}.yml"
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return None


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
            color: #2962ff; /* Electric Blue */
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
        
        </style>
    """, unsafe_allow_html=True)

load_css()

# --- SIDEBAR ---

st.sidebar.header("Otomai Dashboard")

# 1. Status Section
st.sidebar.subheader("Live Status")
running_containers = get_running_containers()
selected_container = None

if running_containers:
    container_names = [f"{c['name']} ({c['strategy']})" for c in running_containers]
    selected_container_name = st.sidebar.selectbox("Select Bot to Monitor", container_names)
    
    # Find selected container object
    for c in running_containers:
        if f"{c['name']} ({c['strategy']})" == selected_container_name:
            selected_container = c
            break
            
    if selected_container:
        # Use custom CSS class if possible, but emojis work well for specific colors
        status_color = "green" if selected_container['status'] == 'running' else "red"
        st.sidebar.markdown(f"**Env**: `{selected_container['env']}`")
        st.sidebar.markdown(f"**Status**: :{status_color}[●] {selected_container['status'].upper()}")
else:
    st.sidebar.warning("No running bot detected.")

# 2. Controls
st.sidebar.divider()
st.sidebar.subheader("History Filters")
engine = get_db_engine()
df = load_trades(engine)

all_strategies = df['strategy'].dropna().unique().tolist() if not df.empty else []
selected_strategy_filter = st.sidebar.selectbox(
    "Filter History by Strategy", 
    ["All"] + all_strategies
)

# --- MAIN PAGE ---

st.title("Trading Performance")

# Metric Cards
if not df.empty:
    filtered_df = df.copy()
    if selected_strategy_filter != "All":
        filtered_df = filtered_df[filtered_df['strategy'] == selected_strategy_filter]

    # Sort by date to get first trade
    filtered_df = filtered_df.sort_values("open_date")
    
    # Calculate Initial Capital from First Trade
    # Assumption: User means the notional value of the first trade (Price * Amount)
    initial_capital = 1000.0 # Default fallback
    if not filtered_df.empty:
        try:
            # Ensure columns are numeric
            first_trade = filtered_df.iloc[0]
            ft_amount = float(first_trade.get('amount', 0) or 0)
            ft_price = float(first_trade.get('open_price', 0) or 0)
            
            calculated_cap = ft_amount * ft_price
            if calculated_cap > 0:
                initial_capital = calculated_cap
        except Exception as e:
            # Fallback
            pass
            
    # Display Capital (Editable)
    st.sidebar.divider()
    initial_capital = st.sidebar.number_input("Initial Capital ($)", min_value=1.0, value=float(initial_capital), step=100.0, help="Auto-detected from first trade size")

    col1, col2, col3, col4, col5 = st.columns(5)
    
    total_trades = len(filtered_df)
    total_pnl = filtered_df['net_profit'].sum()
    total_pnl_pct = (total_pnl / initial_capital) * 100
    
    win_rate = (len(filtered_df[filtered_df['net_profit'] > 0]) / total_trades * 100) if total_trades > 0 else 0
    
    avg_return = filtered_df['net_profit'].mean()
    std_return = filtered_df['net_profit'].std()
    sharpe = (avg_return / std_return) if std_return != 0 else 0

    col1.metric("Total Trades", total_trades)
    col2.metric("Total PnL ($)", f"{total_pnl:.2f}")
    col3.metric("Total PnL (%)", f"{total_pnl_pct:.2f}%")
    col4.metric("Win Rate", f"{win_rate:.1f}%")
    col5.metric("Sharpe (Trade)", f"{sharpe:.2f}")
    
    # Chart
    st.subheader("Cumulative PnL")
    filtered_df = filtered_df.sort_values("close_date")
    filtered_df['cumulative_pnl'] = filtered_df['net_profit'].cumsum()
    
    fig = px.line(filtered_df, x="close_date", y="cumulative_pnl", markers=True, 
                  title=f"Cumulative PnL - {selected_strategy_filter}")
    
    # Finrax Chart Styling
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='#e0e0e0',
        title_font_size=20,
        xaxis=dict(showgrid=True, gridcolor='#2a2e39'),
        yaxis=dict(showgrid=True, gridcolor='#2a2e39'),
    )
    fig.update_traces(line_color='#2962ff', marker_color='#00e676')
                  
    st.plotly_chart(fig, use_container_width=True)
    
    # Table (Expander)
    with st.expander("Recent Trade History", expanded=False):
        st.dataframe(
            filtered_df[['id', 'strategy', 'symbol', 'open_date', 'close_date', 'hold_side', 'open_price', 'close_price', 'net_profit']]
            .sort_values("close_date", ascending=False)
        )
else:
    st.info("No historical trades found in database.")


# --- ACTIVE CONFIG & LIVE DATA ---
st.divider()

col_conf, col_live = st.columns([1, 2])

# Left Column: Config
with col_conf:
    st.subheader("Configuration")
    
    # Default to selected container's config if available
    default_env_idx = 0
    default_strat_idx = 0
    
    conf_envs = ["dev", "prod"]
    
    if selected_container:
        if selected_container['env'] in conf_envs:
            default_env_idx = conf_envs.index(selected_container['env'])
    
    env_sel = st.selectbox("Environment", conf_envs, index=default_env_idx)
    
    # List strategies
    import glob
    files = glob.glob(f"conf/{env_sel}/*.yml")
    strategies = [os.path.basename(f).replace(".yml","") for f in files]
    
    if selected_container and selected_container['strategy'] in strategies:
        default_strat_idx = strategies.index(selected_container['strategy'])
        
    strat_sel = st.selectbox("Strategy Config", strategies, index=default_strat_idx)

    active_config = None
    if strat_sel:
        active_config = load_config(env_sel, strat_sel)
        if active_config:
            with st.expander("View Config Parameters", expanded=True):
                st.json(active_config)
            
            # Extract symbol for live orders
            try:
                target_symbol = active_config.get('strategy', {}).get('symbol')
            except:
                target_symbol = None
        else:
            st.error("Config file not found.")
            target_symbol = None

# Right Column: Live Data
with col_live:
    st.subheader("Live Active Orders")
    
    if target_symbol:
        st.markdown(f"Fetching open orders for **{target_symbol}**...")
        orders, err = get_live_orders(target_symbol)
        
        if err:
            st.error(f"Failed to fetch orders: {err}")
        elif orders:
            # orders is a list of dicts from ccxt
            st.success(f"Found {len(orders)} open orders.")
            
            orders_data = []
            for o in orders:
                orders_data.append({
                    "id": o.get('id'),
                    "symbol": o.get('symbol'),
                    "side": o.get('side'),
                    "type": o.get('type'),
                    "price": o.get('price'),
                    "amount": o.get('amount'),
                    "filled": o.get('filled'),
                    "status": o.get('status'),
                    "datetime": o.get('datetime')
                })
            st.dataframe(pd.DataFrame(orders_data))
        else:
            st.info("No open orders found.")
    else:
        st.warning("Select a valid configuration with a 'symbol' to view live orders.")

# --- LIVE LOGS ---
st.divider()
st.subheader("Live Container Logs")

if selected_container:
    if st.button("Refresh Logs"):
        pass # Rerun app
    
    logs = get_container_logs(selected_container['full_id'])
    st.code(logs, language='text')
else:
    st.info("Select a running bot in the sidebar to view logs.")
