FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y curl

RUN curl -sSL https://install.python-poetry.org | python -

# Put Poetry on the path.
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

COPY pyproject.toml poetry.lock /app/
COPY dist/*.whl /app/
RUN pip install /app/*.whl

COPY src/ /app/src/
COPY conf/ /app/conf/

ENTRYPOINT ["poetry", "run", "otomai"]
