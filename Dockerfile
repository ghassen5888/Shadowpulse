FROM python:3.10-slim

# Set working directory
WORKDIR /app

# 🛠️ FIX 1: Install Tor, curl, and sed (sed handles line-ending fixes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tor \
    sed \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# 🛠️ FIX 2: Create a non-root user
RUN useradd -m -u 1000 shadowuser

# 🛠️ FIX 3: Robust permission and script handling
# 1. Ensure the Tor data directory exists
# 2. Convert Windows line endings to Linux (vital for entrypoint scripts)
# 3. Make the script executable
# 4. Set ownership for everything to our non-root user
RUN mkdir -p /var/lib/tor && \
    sed -i 's/\r$//' /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && \
    chown -R shadowuser:shadowuser /app /var/lib/tor /etc/tor

# Switch to non-root user
USER shadowuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 🛠️ FIX 4: Run the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]