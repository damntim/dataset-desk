FROM python:3.13-slim

WORKDIR /code
ENV PYTHONUNBUFFERED=1

# Copy the package list first: Docker caches this layer,
# so pip only re-runs when the requirements change.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# On every start: 1) update the tables, 2) create demo users, 3) run the API.
# --no-access-log: our own middleware already logs each request as JSON.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
