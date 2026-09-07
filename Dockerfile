# ---- stage 1: build the console ----
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- stage 2: python runtime ----
FROM python:3.11-slim AS runtime
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY agent/ agent/
COPY emitter/ emitter/
COPY gate/ gate/
COPY server/ server/
COPY data/ data/
RUN uv pip install --system --no-cache .

COPY --from=web-build /web/dist/ web/dist/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
