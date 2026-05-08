FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/build.mjs ./
COPY frontend/index.html frontend/app.js frontend/styles.css ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY core ./core
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN pip install --no-cache-dir -e .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
