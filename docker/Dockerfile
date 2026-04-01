FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for TA-Lib and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --build=aarch64-unknown-linux-gnu --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and scripts
COPY src/ ./src/
COPY main.py ./
COPY run_backtest.py ./
COPY config/ ./config/
COPY tests/ ./tests/

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/reports /app/data/stocks

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "main.py", "--help"]