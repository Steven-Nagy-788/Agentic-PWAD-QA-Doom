FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    cmake \
    libboost-all-dev \
    libgl1 \
    libsdl2-dev \
    x11-utils \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8001
CMD ["fastmcp", "run", "src/doom_mcp/server.py", "--transport", "sse", "--host", "0.0.0.0", "--port", "8001", "--path", "/sse"]
