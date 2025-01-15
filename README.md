# Otomai Trading Bot

Otomai is an advanced, modular, and extensible algorithmic trading bot designed for cryptocurrency trading. It supports multiple trading strategies, services like exchanges, database integration, and configurable environments for development, pre-production, and production.

## Features

- **Modular Design**: Each service (e.g., exchange, strategies) is encapsulated and reusable.
- **Environment-Specific Configuration**: Use YAML configuration files for `dev`, `preprod`, and `prod` environments.
- **Strategy Management**: Easily add, modify, or remove trading strategies.
- **Logging and Monitoring**: Comprehensive logging for debugging and monitoring.
- **Docker Support**: Deploy seamlessly with Docker and Docker Compose.
- **Extensibility**: Add new services (e.g., exchanges, notifications) with minimal effort.

---

## Project Structure

```plaintext
.
├── conf/                    # Configuration files for different environments
│   ├── dev/                 # Development-specific configs
│   ├── preprod/             # Pre-production-specific configs
│   ├── prod/                # Production-specific configs
├── env/                     # Virtual environment folder (excluded from Git)
├── src/
│   ├── otomai/
│   │   ├── core/            # Core components and shared logic
│   │   ├── services/        # Services like exchanges, notifications, etc.
│   │   ├── strategies/      # Trading strategies
│   │   │   ├── base.py      # Base class for all strategies
│   │   │   ├── mrat.py      # Example MRAT strategy
│   │   │   ├── utils.py     # Utility functions for strategies
│   ├── configs.py           # Global configuration handling
│   ├── logger.py            # Logger setup
│   ├── scripts.py           # Main script entry point
│   ├── settings.py          # Environment-specific settings
├── docker-compose.yml       # Docker Compose configuration
├── poetry.lock              # Poetry lockfile for dependency management
├── pyproject.toml           # Project and dependency configuration
```
---

## Getting Started

Follow these steps to set up and run Otomai:

### 1. **Clone the Repository**
```
git clone https://github.com/your-repo/otomai.git
cd otomai
```

---

### 2. **Set Up the Environment Using Poetry**

1. Install Poetry if you don't have it:
```
pip install poetry
```
2. Install dependencies:
```
poetry install
```
3. Activate the environment:
```
poetry shell
```

---

### 3. **Set Up Configuration**

#### **Environment Files**
The bot uses environment-specific YAML configuration files in the `conf/` folder. Update the settings in the appropriate YAML file (`dev/config.yaml`, `preprod/config.yaml`, or `prod/config.yaml`) to include:

- API keys for exchanges
- Database connection details
- Logging levels
- Strategy parameters

#### **Environment Variables**
Create `.env` files under the `env/` directory for sensitive information. For example:

**`env/base.env`**
```
EXCHANGE_API_KEY=your_api_key
EXCHANGE_API_SECRET=your_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_token
DATABASE_URL=your_database_url
```

**`env/development.env`**
```
ENV=development
STRATEGY=mrat
```

**`env/production.env`**
```
ENV=production
STRATEGY=mrat
```

---

### 4. **Run the Trading Bot**

#### **With Poetry**
To run a strategy, pass the strategy YAML file:
```
poetry run python src/scripts.py --files strategies/development/mrat.yml
```

#### **With Docker**
You can configure and run the bot dynamically using Docker Compose.

1. Build and run the container:
```
docker-compose up --build
```
2. The bot will dynamically load the appropriate strategy YAML based on the `ENV` and `STRATEGY` environment variables.

---

### 5. **Dynamic Strategy Selection**

The bot can load strategies dynamically using the `STRATEGY` and `ENV` variables. These are passed as environment variables in `docker-compose.yml`:

**`docker-compose.yml`**
```
version: "3.8"
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      # Set the environment dynamically, defaulting to 'development'
      ENV: ${ENV:-development}
      # Set the strategy file dynamically based on ENV
      STRATEGY: ${STRATEGY:-mrat}
    env_file:
      - env/base.env
      - env/${ENV:-development}.env
    volumes:
      - ./strategies:/app/strategies
      - ./env:/app/env
    command: ["python", "src/scripts.py", "--files", "strategies/${ENV}/${STRATEGY}.yml"]
```

---

### 6. **Add a New Strategy**

1. Create a new YAML file for your strategy in the `strategies` directory, organized by environment.
   Example: `strategies/development/my_new_strategy.yml`.

2. Define your strategy configuration in the YAML file:
```
strategy:
  name: my_new_strategy
  parameters:
    param1: value1
    param2: value2
```

3. Add the strategy name in your `.env` file:
```
STRATEGY=my_new_strategy
```

4. Run the bot with your new strategy:
   - **With Poetry**:
     ```
     poetry run python src/scripts.py --files strategies/development/my_new_strategy.yml
     ```
   - **With Docker**:
     ```
     docker-compose up --build
     ```

---

## Logging and Debugging

Logs are stored in the `logs/` folder. You can customize the logging level in `src/logger.py`.

To enable debug-level logging, update your `.env` or YAML config:
```
logging:
  level: DEBUG
```

---

## Contributing

Contributions are welcome! Feel free to:
- Submit pull requests
- Report bugs
- Suggest new features

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contact

For inquiries or support, contact the project maintainers at [thomas_cl@gmx.fr].
