# Calgary OGS Sizing Analysis
# SWMM Continuous Simulation on Railway

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for swmm-toolkit
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Generate rainfall data at build time
RUN python generate_calgary_rainfall.py

# Pre-compute 30-year flows at build time (takes ~4 min, but runtime is instant)
RUN python precompute_flows.py

# Default command: run fast OGS sizing
CMD ["python", "main.py"]

