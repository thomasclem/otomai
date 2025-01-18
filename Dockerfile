FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

COPY dist/*.whl /app/
RUN pip install /app/*.whl

COPY conf/ /app/conf/

ENTRYPOINT ["otomai"]
