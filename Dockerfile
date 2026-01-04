FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Phoenix code
COPY . .

# Create data directory for persistence
RUN mkdir -p /data
ENV PHOENIX_DATA_DIR=/data

# Expose web port
EXPOSE 8080

# Run Phoenix in web mode
CMD ["python", "main.py", "--mode", "web", "--port", "8080"]
