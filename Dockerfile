FROM python:3.11-slim

WORKDIR /app

# Install Node.js, npm, and Chromium for mermaid-cli
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Install mermaid-cli globally
RUN npm install -g @mermaid-js/mermaid-cli

# Set Puppeteer executable path for Docker environment
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY sync_to_google.py .

# Make script executable
RUN chmod +x sync_to_google.py

# Run sync script
CMD ["python", "sync_to_google.py"]
