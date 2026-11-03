# Otomai Trading Bot

Otomai is an advanced, modular, and extensible algorithmic trading bot designed for cryptocurrency trading. It supports multiple trading strategies, services like exchanges, database integration, and configurable environments for development, pre-production, and production.

## Features

- **Modular Design**: Each service (e.g., exchange, strategies) is encapsulated and reusable
- **Position Monitoring Service**: Dedicated service for tracking position lifecycle
- **Environment-Specific Configuration**: Use YAML configuration files for `dev`, `preprod`, and `prod` environments
- **Strategy Management**: Easily add, modify, or remove trading strategies
- **Comprehensive Logging**: Structured logging for debugging and monitoring
- **Type Safety**: Full Pydantic validation throughout
- **Extensibility**: Add new services (e.g., exchanges, notifications) with minimal effort

---

## Quick Start

### 1. Install UV

```powershell
# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone & Setup

```bash
git clone https://github.com/your-repo/otomai.git
cd otomai

# Install dependencies
uv sync
```

### 3. Configure

Create `env/dev.env`:
```env
ENV=dev
BITGET_API_KEY=your_api_key
BITGET_SECRET=your_secret
BITGET_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_telegram_token
```

### 4. Run

```bash
uv run python src/otomai/scripts.py --files conf/dev/mrat_zscore.yml
```

---

## Documentation

### BingX listing-volume short

The strategy trades live on a dedicated BingX sub-account. Export `BINGX_API_KEY` and
`BINGX_SECRET` for that sub-account, then:

```bash
uv run otomai --files conf/dev/listing_volume_short.yml --check-config
uv run otomai --files conf/dev/listing_volume_short.yml
```

It shorts high-volume new BingX listings on the first eligible quote after four
closed hourly bars, with a 20% stop, 60% target and 21-day time exit. There is no
additional one-hour wait; the default entry grace is 120 seconds.
Defaults allocate 5% of current equity as notional, with 30% gross and 10% listing-day
admission caps. Positions and orders are read from BingX; listing history and entry
intents survive restarts in SQLite. See the
[strategy and operations guide](docs/strategies/listing_volume_short.md).

📚 **[Full Documentation](docs/README.md)**

- **[Installation Guide](docs/installation.md)** - Detailed setup instructions
- **[Fresh Bazzite Server Setup](docs/deployment/bazzite_cockpit_cloudflare.md)** - Recreate Cockpit, Podman and Cloudflare access
- **[Bazzite / Podman Deployment](docs/deployment/linux_bazzite_podman.md)** - Run through Cockpit with persistent state
- **[Windows Server Deployment](docs/deployment/windows_server.md)** - Run as Windows Service
- **[Architecture Overview](docs/architecture/overview.md)** - System design
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

---

## Project Structure

```plaintext
.
├── conf/                    # Configuration files for different environments
│   ├── dev/                 # Development configs
│   ├── preprod/             # Pre-production configs
│   └── prod/                # Production configs
├── docs/                    # Documentation
├── src/otomai/
│   ├── core/               # Domain: models, shared params, sizing, indicators (no I/O)
│   ├── ports/              # Interfaces: Exchange, Notifier, Database
│   ├── adapters/           # Implementations: exchanges (CCXT, Bitget, BingX), notifiers, databases, scrapers
│   ├── services/           # Shared application logic: order placement, position monitor
│   ├── strategies/         # One module or package per strategy, with its own params
│   └── settings.py         # Composition: YAML -> strategy and its adapters
├── tests/                  # Test suite
├── pyproject.toml          # UV/Python project configuration
└── uv.lock                # UV lockfile
```

---

## Development

### Run Tests

```bash
uv run pytest tests/ -v
```

### Code Quality

```bash
# Linting
uv run ruff check src/

# Type checking
uv run mypy src/otomai
```

### Pre-commit Hooks

```bash
uv pip install pre-commit
pre-commit install
```

---

## Key Improvements (v2.0.1)

- ✅ Listing-volume short: the API key alone identifies the sub-account (no `account_label`); entry is due at the decision (no `entry_delay_hours`)
- ✅ `order_timeout` from the YAML now bounds how long the position monitor waits for an entry to fill
- ✅ One order-submission path in the CCXT adapter; stop orders translate margin rejections too
- ✅ Dead code and the dashboard's `streamlit`/`docker` dependencies removed

### v2.0.0

- ✅ Hexagonal architecture: core, ports, adapters, services and strategies, with enforced layer import rules
- ✅ New BingX listing-volume short strategy (replaces `listing_backrun`, now removed)
- ✅ Lock-based app-only container and docker-compose worker selected by `STRATEGY`/`ENV`
- ✅ Bazzite deployment guides (Cockpit + Cloudflare, Podman Compose and Quadlet)
- ✅ Local SQLite state database
- ✅ Migrated from Poetry to UV

---

## Contributing

Contributions are welcome! See [Contributing Guide](docs/development/contributing.md).

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contact

For inquiries or support, contact the project maintainers at [thomas_cl@gmx.fr](mailto:thomas_cl@gmx.fr).
