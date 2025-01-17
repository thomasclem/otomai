FROM python:3.11-slim

WORKDIR /app

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

COPY dist/*.whl /app/
RUN pip install /app/*.whl

COPY src/ /app/src/
COPY conf/ /app/conf/

ENTRYPOINT ["poetry", "run", "otomai"]
