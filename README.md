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
uv run python src/otomai/scripts.py --files conf/dev/listing_backrun.yml
```

---

## Documentation

📚 **[Full Documentation](docs/README.md)**

- **[Installation Guide](docs/installation.md)** - Detailed setup instructions
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
│   ├── core/               # Core components and shared logic
│   │   ├── constants.py    # Centralized constants
│   │   ├── exceptions.py   # Custom exceptions
│   │   └── utils.py        # Utility functions
│   ├── services/           # Services (exchange, database, notifier, position monitor)
│   └── strategies/         # Trading strategies
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

## Key Improvements (v1.0.1)

- ✅ Migrated from Poetry to UV (faster dependency resolution)
- ✅ Created Position Monitor service (separation of concerns)
- ✅ Centralized constants and custom exceptions
- ✅ Fixed infinite loops in exchange service
- ✅ Added comprehensive Windows Server deployment guide
- ✅ Improved error handling throughout

---

## Contributing

Contributions are welcome! See [Contributing Guide](docs/development/contributing.md).

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contact

For inquiries or support, contact the project maintainers at [thomas_cl@gmx.fr](mailto:thomas_cl@gmx.fr).
