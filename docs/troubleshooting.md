# Troubleshooting

## Installation Issues

### UV Not Found
```powershell
# Ensure UV is in PATH
$env:PATH += ";$HOME\.local\bin"

# Or reinstall
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Dependency Conflicts
```bash
# Clear UV cache
uv cache clean

# Reinstall
uv sync --reinstall
```

## Runtime Issues

### Exchange Connection Errors

**Symptom**: `ExchangeConnectionError: Failed to fetch markets`

**Solution**:
1. Check internet connection
2. Verify API keys in `env/*.env`
3. Check exchange status
4. Review max retries in `constants.py`

### Position Monitoring Timeout

**Symptom**: `PositionTimeoutError`

**Solution**:
1. Increase timeout in `core/constants.py`:
   ```python
   POSITION_OPENING_TIMEOUT = 1200  # 20 minutes
   ```
2. Check exchange order status manually
3. Verify sufficient balance

### Configuration Errors

**Symptom**: `InvalidConfigurationError`

**Solution**:
1. Validate YAML syntax
2. Check required fields match schema
3. Review `conf/dev/listing_backrun.yml` example

## Windows Service Issues

**Service Won't Start**:
```powershell
# Check NSSM logs
type C:\otomai\logs\stderr.log

# Test manual run
cd C:\otomai
uv run python src/otomai/scripts.py --files conf/prod/listing_backrun.yml
```

**Service Crashes**:
1. Check Windows Event Viewer
2. Review application logs
3. Verify Python path in service config

## Common Errors

### ModuleNotFoundError
```bash
# Reinstall dependencies
uv sync
```

### API Rate Limiting
- Reduce request frequency in constants
- Add delays between operations
- Check exchange rate limits

## Getting Help

1. Check [GitHub Issues](https://github.com/your-repo/otomai/issues)
2. Review logs in `logs/` directory
3. Enable DEBUG logging in configuration
