"""
Enhanced Big Drop Strategy Analysis Module

This module provides comprehensive analysis tools for the big drop trading strategy,
including statistical tests, risk metrics, portfolio simulation, and visualizations.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from scipy import stats
from scipy.stats import ttest_ind, mannwhitneyu
import warnings
warnings.filterwarnings('ignore')


class StatisticalAnalyzer:
    """Statistical analysis tools for strategy evaluation"""
    
    @staticmethod
    def calculate_confidence_interval(data, confidence=0.95):
        """Calculate confidence interval for data"""
        if len(data) == 0:
            return np.nan, np.nan, np.nan
        
        mean = np.mean(data)
        se = stats.sem(data)
        interval = se * stats.t.ppf((1 + confidence) / 2, len(data) - 1)
        return mean, mean - interval, mean + interval
    
    @staticmethod
    def test_significance(group1, group2, test_type='ttest'):
        """
        Test statistical significance between two groups
        
        Parameters:
        - test_type: 'ttest' or 'mannwhitney'
        """
        group1_clean = group1.dropna()
        group2_clean = group2.dropna()
        
        if len(group1_clean) < 2 or len(group2_clean) < 2:
            return np.nan, np.nan
        
        if test_type == 'ttest':
            statistic, p_value = ttest_ind(group1_clean, group2_clean)
        else:
            statistic, p_value = mannwhitneyu(group1_clean, group2_clean)
        
        return statistic, p_value
    
    @staticmethod
    def correlation_with_significance(x, y):
        """Calculate correlation with p-value"""
        x_clean = x.dropna()
        y_clean = y.dropna()
        
        # Align the data
        valid_idx = x_clean.index.intersection(y_clean.index)
        if len(valid_idx) < 3:
            return np.nan, np.nan
        
        corr, p_value = stats.pearsonr(x_clean.loc[valid_idx], y_clean.loc[valid_idx])
        return corr, p_value


class RiskMetrics:
    """Calculate various risk-adjusted performance metrics"""
    
    @staticmethod
    def sharpe_ratio(returns, risk_free_rate=0):
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return np.nan
        return (returns.mean() - risk_free_rate) / returns.std()
    
    @staticmethod
    def sortino_ratio(returns, risk_free_rate=0):
        """Calculate Sortino ratio (uses only downside deviation)"""
        if len(returns) == 0:
            return np.nan
        
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return np.nan
        
        return (returns.mean() - risk_free_rate) / downside_returns.std()
    
    @staticmethod
    def max_drawdown(returns):
        """Calculate maximum drawdown"""
        if len(returns) == 0:
            return np.nan
        
        cumulative = (1 + returns / 100).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100
        return drawdown.min()
    
    @staticmethod
    def max_consecutive_losses(returns):
        """Calculate maximum consecutive losses"""
        if len(returns) == 0:
            return 0
        
        losses = returns < 0
        consecutive = 0
        max_consecutive = 0
        
        for loss in losses:
            if loss:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        
        return max_consecutive
    
    @staticmethod
    def value_at_risk(returns, confidence=0.95):
        """Calculate Value at Risk (VaR)"""
        if len(returns) == 0:
            return np.nan
        return np.percentile(returns, (1 - confidence) * 100)
    
    @staticmethod
    def conditional_value_at_risk(returns, confidence=0.95):
        """Calculate Conditional Value at Risk (CVaR/Expected Shortfall)"""
        if len(returns) == 0:
            return np.nan
        var = np.percentile(returns, (1 - confidence) * 100)
        return returns[returns <= var].mean()


class StrategyAnalyzer:
    """Comprehensive strategy analysis and backtesting"""
    
    def __init__(self, df):
        """
        Initialize with dataframe containing first candle analysis results
        
        Expected columns: symbol, first_candle_perf, perf_4h, perf_8h, perf_12h, 
                         perf_24h, perf_48h, final_perf, btc_vol, volume_usdt_btc_prop, etc.
        """
        self.df = df.copy()
        self.stats = StatisticalAnalyzer()
        self.risk = RiskMetrics()
    
    def calculate_win_rate(self, returns_col='final_perf'):
        """Calculate win rate"""
        return (self.df[returns_col] > 0).mean() * 100
    
    def calculate_profit_factor(self, returns_col='final_perf'):
        """Calculate profit factor"""
        wins = self.df[self.df[returns_col] > 0][returns_col]
        losses = self.df[self.df[returns_col] < 0][returns_col]
        
        if len(losses) == 0 or losses.sum() == 0:
            return np.inf if len(wins) > 0 else 0
        
        return abs(wins.sum() / losses.sum())
    
    def analyze_by_threshold(self, threshold, returns_col='perf_7d'):
        """Analyze performance for a specific entry threshold"""
        subset = self.df[self.df['first_candle_perf'] <= threshold]
        
        if len(subset) == 0:
            return None
        
        returns = subset[returns_col].dropna()
        
        mean, lower_ci, upper_ci = self.stats.calculate_confidence_interval(returns)
        
        return {
            'threshold': threshold,
            'n_trades': len(subset),
            'win_rate': (returns > 0).mean() * 100,
            'avg_return': returns.mean(),
            'median_return': returns.median(),
            'std_return': returns.std(),
            'best_trade': returns.max(),
            'worst_trade': returns.min(),
            'sharpe': self.risk.sharpe_ratio(returns),
            'sortino': self.risk.sortino_ratio(returns),
            'max_drawdown': self.risk.max_drawdown(returns),
            'profit_factor': abs(returns[returns > 0].sum() / returns[returns < 0].sum()) if len(returns[returns < 0]) > 0 else np.inf,
            'ci_lower': lower_ci,
            'ci_upper': upper_ci,
            'var_95': self.risk.value_at_risk(returns),
            'cvar_95': self.risk.conditional_value_at_risk(returns),
        }
    
    def scan_thresholds(self, thresholds=None, returns_col='perf_7d'):
        """Scan multiple entry thresholds and return comparison"""
        if thresholds is None:
            thresholds = [-50, -40, -30, -25, -20, -15, -10, -5, 0]
        
        results = []
        for threshold in thresholds:
            result = self.analyze_by_threshold(threshold, returns_col)
            if result:
                results.append(result)
        
        return pd.DataFrame(results)
    
    def segment_by_btc_market(self):
        """Segment analysis by BTC market conditions"""
        self.df['btc_market'] = pd.cut(
            self.df['btc_vol'],
            bins=[-np.inf, -2, 2, np.inf],
            labels=['Bear(<-2%)', 'Sideways(-2% to 2%)', 'Bull(>2%)']
        )
        
        segments = {}
        for market in self.df['btc_market'].unique():
            if pd.notna(market):
                subset = self.df[self.df['btc_market'] == market]
                segments[market] = {
                    'count': len(subset),
                    'win_rate_24h': (subset['perf_24h'] > 0).mean() * 100,
                    'avg_return_24h': subset['perf_24h'].mean(),
                    'median_return_24h': subset['perf_24h'].median(),
                }
        
        return pd.DataFrame(segments).T
    
    def segment_by_volume(self, quantiles=4):
        """Segment analysis by volume proportions"""
        self.df['volume_segment'] = pd.qcut(
            self.df['volume_usdt_btc_prop'],
            q=quantiles,
            labels=[f'Q{i+1}' for i in range(quantiles)],
            duplicates='drop'
        )
        
        segments = {}
        for vol_seg in self.df['volume_segment'].unique():
            if pd.notna(vol_seg):
                subset = self.df[self.df['volume_segment'] == vol_seg]
                segments[vol_seg] = {
                    'count': len(subset),
                    'win_rate_24h': (subset['perf_24h'] > 0).mean() * 100,
                    'avg_return_24h': subset['perf_24h'].mean(),
                    'sharpe_24h': self.risk.sharpe_ratio(subset['perf_24h'].dropna()),
                }
        
        return pd.DataFrame(segments).T
    
    def find_optimal_holding_period(self, threshold=-20):
        """Find optimal holding period for given entry threshold"""
        subset = self.df[self.df['first_candle_perf'] <= threshold]
        
        periods = {}
        for period_col in ['perf_4h', 'perf_8h', 'perf_12h', 'perf_24h', 'perf_48h', 'final_perf']:
            if period_col in subset.columns:
                returns = subset[period_col].dropna()
                periods[period_col.replace('perf_', '')] = {
                    'avg_return': returns.mean(),
                    'win_rate': (returns > 0).mean() * 100,
                    'sharpe': self.risk.sharpe_ratio(returns),
                    'profit_factor': abs(returns[returns > 0].sum() / returns[returns < 0].sum()) if len(returns[returns < 0]) > 0 else np.inf,
                }
        
        return pd.DataFrame(periods).T


class PortfolioSimulator:
    """Backtest portfolio performance with various strategies"""
    
    def __init__(self, df, initial_capital=10000):
        """Initialize portfolio simulator"""
        self.df = df.copy()
        self.initial_capital = initial_capital
        self.risk = RiskMetrics()
    
    def simulate_strategy(self, entry_threshold=-20, holding_period='7d',
                         stop_loss=None, take_profit=None, 
                         position_size=1000, max_positions=10, position_type='long'):
        """
        Simulate strategy with specific parameters
        
        Parameters:
        - entry_threshold: Entry when first_candle_perf <= this value
        - holding_period: '7d', '14d', '30d', or 'final'
        - stop_loss: Stop loss percentage (e.g., -30)
        - take_profit: Take profit percentage (e.g., 50)
        - position_size: Dollar amount per position
        - max_positions: Maximum concurrent positions
        - position_type: 'long' or 'short' - for short positions, returns are inverted
        """
        # Filter entries
        entries = self.df[self.df['first_candle_perf'] <= entry_threshold].copy()
        
        if len(entries) == 0:
            return None
        
        # Determine returns column
        returns_col = f"perf_{holding_period}" if holding_period != 'final' else 'final_perf'
        
        if returns_col not in entries.columns:
            return None
        
        # Calculate position returns
        # For short positions, invert the returns (profit when price goes down)
        if position_type == 'short':
            entries['position_return_pct'] = -entries[returns_col]
        else:
            entries['position_return_pct'] = entries[returns_col]
        
        # Apply stop-loss and take-profit
        if stop_loss is not None:
            entries.loc[entries['position_return_pct'] < stop_loss, 'position_return_pct'] = stop_loss
        if take_profit is not None:
            entries.loc[entries['position_return_pct'] > take_profit, 'position_return_pct'] = take_profit
        
        # Calculate dollar returns
        entries['position_return_dollar'] = position_size * entries['position_return_pct'] / 100
        
        # Portfolio metrics
        total_return_dollar = entries['position_return_dollar'].sum()
        total_return_pct = (total_return_dollar / position_size / len(entries)) * 100
        
        wins = entries[entries['position_return_pct'] > 0]
        losses = entries[entries['position_return_pct'] < 0]
        
        return {
            'total_trades': len(entries),
            'total_return_dollar': total_return_dollar,
            'total_return_pct': total_return_pct,
            'win_rate': len(wins) / len(entries) * 100,
            'avg_win': wins['position_return_pct'].mean() if len(wins) > 0 else 0,
            'avg_loss': losses['position_return_pct'].mean() if len(losses) > 0 else 0,
            'best_trade': entries['position_return_pct'].max(),
            'worst_trade': entries['position_return_pct'].min(),
            'sharpe': self.risk.sharpe_ratio(entries['position_return_pct']),
            'sortino': self.risk.sortino_ratio(entries['position_return_pct']),
            'max_drawdown': self.risk.max_drawdown(entries['position_return_pct']),
            'profit_factor': abs(wins['position_return_pct'].sum() / losses['position_return_pct'].sum()) if len(losses) > 0 and losses['position_return_pct'].sum() != 0 else np.inf,
            'max_consecutive_losses': self.risk.max_consecutive_losses(entries['position_return_pct']),
            'position_type': position_type,
        }
    
    def simulate_short_strategy(self, entry_threshold=0, holding_period='7d',
                               stop_loss=None, take_profit=None, 
                               position_size=1000, max_positions=10):
        """
        Simulate SHORT strategy - only enter positions on NEGATIVE first candles
        Returns are inverted to simulate profit from price decline
        
        Parameters:
        - entry_threshold: Entry when first_candle_perf <= this value (default 0 for negative candles only)
        - holding_period: '4h', '8h', '12h', '24h', '48h', or 'final'
        - stop_loss: Stop loss percentage (e.g., -30)
        - take_profit: Take profit percentage (e.g., 50)
        - position_size: Dollar amount per position
        - max_positions: Maximum concurrent positions
        """
        # Filter for NEGATIVE first candles only
        entries = self.df[self.df['first_candle_perf'] < 0].copy()
        
        # Apply threshold if stricter than 0
        if entry_threshold < 0:
            entries = entries[entries['first_candle_perf'] <= entry_threshold]
        
        if len(entries) == 0:
            return None
        
        # Determine returns column
        returns_col = f"perf_{holding_period}" if holding_period != 'final' else 'final_perf'
        
        if returns_col not in entries.columns:
            return None
        
        # SHORT POSITION: Invert returns (profit when price goes down)
        entries['position_return_pct'] = -entries[returns_col]
        
        # Apply stop-loss and take-profit
        if stop_loss is not None:
            entries.loc[entries['position_return_pct'] < stop_loss, 'position_return_pct'] = stop_loss
        if take_profit is not None:
            entries.loc[entries['position_return_pct'] > take_profit, 'position_return_pct'] = take_profit
        
        # Calculate dollar returns
        entries['position_return_dollar'] = position_size * entries['position_return_pct'] / 100
        
        # Portfolio metrics
        total_return_dollar = entries['position_return_dollar'].sum()
        total_return_pct = (total_return_dollar / position_size / len(entries)) * 100
        
        wins = entries[entries['position_return_pct'] > 0]
        losses = entries[entries['position_return_pct'] < 0]
        
        return {
            'total_trades': len(entries),
            'total_return_dollar': total_return_dollar,
            'total_return_pct': total_return_pct,
            'win_rate': len(wins) / len(entries) * 100,
            'avg_win': wins['position_return_pct'].mean() if len(wins) > 0 else 0,
            'avg_loss': losses['position_return_pct'].mean() if len(losses) > 0 else 0,
            'best_trade': entries['position_return_pct'].max(),
            'worst_trade': entries['position_return_pct'].min(),
            'sharpe': self.risk.sharpe_ratio(entries['position_return_pct']),
            'sortino': self.risk.sortino_ratio(entries['position_return_pct']),
            'max_drawdown': self.risk.max_drawdown(entries['position_return_pct']),
            'profit_factor': abs(wins['position_return_pct'].sum() / losses['position_return_pct'].sum()) if len(losses) > 0 and losses['position_return_pct'].sum() != 0 else np.inf,
            'max_consecutive_losses': self.risk.max_consecutive_losses(entries['position_return_pct']),
            'position_type': 'short',
        }
    
    def optimize_parameters(self, thresholds=None, holding_periods=None, stop_losses=None):
        """Test multiple parameter combinations"""
        if thresholds is None:
            thresholds = [-40, -30, -20, -10]
        if holding_periods is None:
            holding_periods = ['4h', '8h', '12h', '24h', '48h']
        if stop_losses is None:
            stop_losses = [None, -50, -40, -30]
        
        results = []
        for threshold in thresholds:
            for period in holding_periods:
                for sl in stop_losses:
                    sim = self.simulate_strategy(
                        entry_threshold=threshold,
                        holding_period=period,
                        stop_loss=sl
                    )
                    if sim:
                        sim['entry_threshold'] = threshold
                        sim['holding_period'] = period
                        sim['stop_loss'] = sl
                        results.append(sim)
        
        if len(results) == 0:
            print("WARNING: No valid parameter combinations found!")
            print("Available columns in DataFrame:", self.df.columns.tolist())
            print("Holding periods attempted:", holding_periods)
            print("Make sure your DataFrame has the corresponding perf_* columns.")
        
        return pd.DataFrame(results)


class EnhancedVisualizer:
    """Create interactive visualizations for strategy analysis"""
    
    @staticmethod
    def plot_threshold_comparison(threshold_df):
        """Interactive plot comparing different thresholds"""
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Win Rate by Threshold', 'Average Return', 
                          'Sharpe Ratio', 'Profit Factor'),
            specs=[[{'secondary_y': False}, {'secondary_y': False}],
                   [{'secondary_y': False}, {'secondary_y': False}]]
        )
        
        # Win Rate
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=threshold_df['win_rate'],
                      mode='lines+markers', name='Win Rate',
                      line=dict(color='#00ff00', width=3)),
            row=1, col=1
        )
        
        # Average Return with CI
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=threshold_df['avg_return'],
                      mode='lines+markers', name='Avg Return',
                      line=dict(color='#1f77b4', width=3)),
            row=1, col=2
        )
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=threshold_df['ci_upper'],
                      mode='lines', name='CI Upper',
                      line=dict(width=0), showlegend=False),
            row=1, col=2
        )
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=threshold_df['ci_lower'],
                      mode='lines', name='CI Lower',
                      fill='tonexty', line=dict(width=0),
                      fillcolor='rgba(31, 119, 180, 0.2)', showlegend=False),
            row=1, col=2
        )
        
        # Sharpe Ratio
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=threshold_df['sharpe'],
                      mode='lines+markers', name='Sharpe',
                      line=dict(color='#ff7f0e', width=3)),
            row=2, col=1
        )
        
        # Profit Factor
        profit_factor_capped = threshold_df['profit_factor'].replace([np.inf, -np.inf], np.nan).fillna(10)
        fig.add_trace(
            go.Scatter(x=threshold_df['threshold'], y=profit_factor_capped,
                      mode='lines+markers', name='Profit Factor',
                      line=dict(color='#d62728', width=3)),
            row=2, col=2
        )
        
        fig.update_layout(
            height=800,
            showlegend=True,
            title_text="Strategy Performance by Entry Threshold",
            template='plotly_dark'
        )
        
        fig.update_xaxes(title_text="Entry Threshold (%)", row=2, col=1)
        fig.update_xaxes(title_text="Entry Threshold (%)", row=2, col=2)
        fig.update_yaxes(title_text="Win Rate (%)", row=1, col=1)
        fig.update_yaxes(title_text="Avg Return (%)", row=1, col=2)
        fig.update_yaxes(title_text="Sharpe Ratio", row=2, col=1)
        fig.update_yaxes(title_text="Profit Factor", row=2, col=2)
        
        return fig
    
    @staticmethod
    def plot_performance_heatmap(df):
        """Create heatmap of performance by first candle perf and volume"""
        # Create bins
        df_plot = df.copy()
        df_plot['first_candle_bin'] = pd.cut(df_plot['first_candle_perf'], bins=10)
        df_plot['volume_bin'] = pd.qcut(df_plot['volume_usdt_btc_prop'], q=5, duplicates='drop')
        
        # Aggregate
        heatmap_data = df_plot.groupby(['first_candle_bin', 'volume_bin'])['final_perf'].mean().unstack()
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.values,
            x=[str(x) for x in heatmap_data.columns],
            y=[str(y) for y in heatmap_data.index],
            colorscale='RdYlGn',
            zmid=0,
            text=heatmap_data.values,
            texttemplate='%{text:.1f}%',
            textfont={"size": 10},
            colorbar=dict(title="Avg 7d Return (%)")
        ))
        
        fig.update_layout(
            title='Performance Heatmap: First Candle % vs Volume',
            xaxis_title='Volume Quintile (vs BTC)',
            yaxis_title='First Candle Performance Range',
            height=600,
            template='plotly_dark'
        )
        
        return fig
    
    @staticmethod
    def plot_parameter_optimization(optimization_df):
        """3D plot of parameter optimization results"""
        # Handle negative and NaN Sharpe ratios for marker size
        sharpe_size = optimization_df['sharpe'].fillna(0).abs() * 5 + 5  # Min size of 5
        
        fig = go.Figure(data=[go.Scatter3d(
            x=optimization_df['entry_threshold'],
            y=optimization_df['holding_period'].astype(str),
            z=optimization_df['total_return_pct'],
            mode='markers',
            marker=dict(
                size=sharpe_size,
                color=optimization_df['total_return_pct'],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Total Return %")
            ),
            text=[f"Threshold: {t}<br>Period: {p}<br>SL: {sl}<br>Return: {r:.1f}%<br>Sharpe: {s:.2f}"
                  for t, p, sl, r, s in zip(
                      optimization_df['entry_threshold'],
                      optimization_df['holding_period'],
                      optimization_df['stop_loss'],
                      optimization_df['total_return_pct'],
                      optimization_df['sharpe']
                  )],
            hovertemplate='%{text}<extra></extra>'
        )])
        
        fig.update_layout(
            title='Parameter Optimization Results',
            scene=dict(
                xaxis_title='Entry Threshold',
                yaxis_title='Holding Period',
                zaxis_title='Total Return %'
            ),
            height=700,
            template='plotly_dark'
        )
        
        return fig
    
    @staticmethod
    def plot_equity_curve(simulation_results, df):
        """Plot cumulative equity curve"""
        # Reconstruct trades based on simulation
        entries = df[df['first_candle_perf'] <= simulation_results['entry_threshold']].copy()
        
        # Cumulative returns
        entries = entries.sort_values('index') if 'index' in entries.columns else entries
        entries['cumulative_return'] = (1 + entries['final_perf'] / 100).cumprod() - 1
        entries['cumulative_return'] *= 100  # Convert to percentage
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            y=entries['cumulative_return'],
            mode='lines',
            name='Strategy',
            line=dict(color='#00ff00', width=2)
        ))
        
        # Add benchmark (0% line)
        fig.add_hline(y=0, line_dash="dash", line_color="white", annotation_text="Breakeven")
        
        fig.update_layout(
            title='Cumulative Strategy Returns',
            xaxis_title='Trade Number',
            yaxis_title='Cumulative Return (%)',
            height=500,
            template='plotly_dark',
            hovermode='x unified'
        )
        
        return fig


def generate_comprehensive_report(df):
    """Generate a comprehensive analysis report"""
    analyzer = StrategyAnalyzer(df)
    simulator = PortfolioSimulator(df)
    visualizer = EnhancedVisualizer()
    
    print("=" * 80)
    print("COMPREHENSIVE BIG DROP STRATEGY ANALYSIS REPORT")
    print("=" * 80)
    
    # 1. Overall Statistics
    print("\n" + "=" * 80)
    print("1. OVERALL STATISTICS")
    print("=" * 80)
    print(f"Total coins analyzed: {len(df)}")
    print(f"Date range: {df['index'].min() if 'index' in df.columns else 'N/A'} to {df['index'].max() if 'index' in df.columns else 'N/A'}")
    print(f"\nFirst Candle Performance:")
    print(f"  Mean: {df['first_candle_perf'].mean():.2f}%")
    print(f"  Median: {df['first_candle_perf'].median():.2f}%")
    print(f"  Std Dev: {df['first_candle_perf'].std():.2f}%")
    print(f"  Min: {df['first_candle_perf'].min():.2f}%")
    print(f"  Max: {df['first_candle_perf'].max():.2f}%")
    
    # 2. Win Rates by Period
    print("\n" + "=" * 80)
    print("2. WIN RATES BY HOLDING PERIOD")
    print("=" * 80)
    for period in ['perf_4h', 'perf_8h', 'perf_12h', 'perf_24h', 'perf_48h', 'final_perf']:
        if period in df.columns:
            win_rate = analyzer.calculate_win_rate(period)
            avg_return = df[period].mean()
            print(f"{period:15s}: {win_rate:6.2f}% win rate | {avg_return:8.2f}% avg return")
    
    # 3. Threshold Analysis
    print("\n" + "=" * 80)
    print("3. PERFORMANCE BY ENTRY THRESHOLD (24h holding)")
    print("=" * 80)
    threshold_analysis = analyzer.scan_thresholds(returns_col='perf_24h')
    print(threshold_analysis[['threshold', 'n_trades', 'win_rate', 'avg_return', 'sharpe', 'profit_factor']].to_string(index=False))
    
    # 4. Market Segmentation
    print("\n" + "=" * 80)
    print("4. PERFORMANCE BY BTC MARKET CONDITIONS")
    print("=" * 80)
    btc_segments = analyzer.segment_by_btc_market()
    print(btc_segments.to_string())
    
    # 5. Volume Segmentation
    print("\n" + "=" * 80)
    print("5. PERFORMANCE BY VOLUME SEGMENTS")
    print("=" * 80)
    vol_segments = analyzer.segment_by_volume()
    print(vol_segments.to_string())
    
    # 6. Optimal Holding Period
    print("\n" + "=" * 80)
    print("6. OPTIMAL HOLDING PERIOD (Entry threshold: -20%)")
    print("=" * 80)
    holding_analysis = analyzer.find_optimal_holding_period(threshold=-20)
    print(holding_analysis.to_string())
    
    # 7. Best Strategy Simulation
    print("\n" + "=" * 80)
    print("7. PORTFOLIO SIMULATION - RECOMMENDED STRATEGY")
    print("=" * 80)
    best_sim = simulator.simulate_strategy(
        entry_threshold=-20,
        holding_period='24h',
        stop_loss=-40,
        take_profit=None,
        position_size=1000
    )
    if best_sim:
        for key, value in best_sim.items():
            if isinstance(value, (int, float)):
                print(f"{key:30s}: {value:10.2f}")
    
    # 8. Statistical Significance
    print("\n" + "=" * 80)
    print("8. STATISTICAL SIGNIFICANCE TESTS")
    print("=" * 80)
    
    # Test if threshold <-20% performs significantly better than baseline
    stats_analyzer = StatisticalAnalyzer()
    threshold_group = df[df['first_candle_perf'] <= -20]['perf_24h']
    baseline_group = df[df['first_candle_perf'] > -20]['perf_24h']
    
    _, p_value = stats_analyzer.test_significance(threshold_group, baseline_group)
    print(f"Threshold <-20% vs Others:")
    print(f"  Mean return (threshold group): {threshold_group.mean():.2f}%")
    print(f"  Mean return (baseline group): {baseline_group.mean():.2f}%")
    print(f"  P-value: {p_value:.4f}")
    print(f"  Significant at 0.05 level: {'Yes' if p_value < 0.05 else 'No'}")
    
    # Correlation analysis
    corr, p_val = stats_analyzer.correlation_with_significance(
        df['first_candle_perf'], df['perf_24h']
    )
    print(f"\nCorrelation (First Candle % vs 24h Return):")
    print(f"  Correlation: {corr:.3f}")
    print(f"  P-value: {p_val:.4f}")
    print(f"  Significant: {'Yes' if p_val < 0.05 else 'No'}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    
    return {
        'threshold_analysis': threshold_analysis,
        'btc_segments': btc_segments,
        'vol_segments': vol_segments,
        'holding_analysis': holding_analysis,
        'best_simulation': best_sim
    }
