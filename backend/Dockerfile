FROM python:3.13-slim

WORKDIR /code
ENV PYTHONUNBUFFERED=1

# Copy the package list first: Docker caches this layer,
# so pip only re-runs when the requirements change.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# --no-access-log: our own middleware already logs each request as JSON.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
