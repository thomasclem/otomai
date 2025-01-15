FROM python:3.11-slim

WORKDIR /app

COPY dist/*.whl /app/
RUN pip install /app/*.whl

COPY src/ /app/src/
COPY conf/ /app/conf/

ENTRYPOINT ["poetry", "run", "otomai"]
