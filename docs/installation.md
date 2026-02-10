# Installation Guide

## Prerequisites

- Python 3.11 or higher
- Windows, Linux, or macOS

## Installing UV

### Windows

```powershell
# Using PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Linux/macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Project Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/otomai.git
cd otomai
```

### 2. Install Dependencies

```bash
# Create virtual environment and install dependencies
uv sync

# Or install in editable mode
uv pip install -e .
```

### 3. Configure Environment Variables

Create environment files in the `env/` directory:

**`env/dev.env`**:
```env
ENV=dev
BITGET_API_KEY=your_api_key
BITGET_SECRET=your_secret
BITGET_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_telegram_token
```

### 4. Run the Bot

```bash
# Run with UV
uv run python src/otomai/scripts.py --files conf/dev/listing_backrun.yml
```

## Migrating from Poetry

If you previously used Poetry:

1. Remove Poetry lock file (already done)
2. Uninstall Poetry dependencies: `poetry env remove --all`
3. Use UV commands going forward

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md) for common installation issues.
