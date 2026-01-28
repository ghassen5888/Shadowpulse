#!/bin/bash

# Start Tor in the background
echo "🛡️ Starting Tor proxy..."
tor --SocksPort 9050 --DataDirectory /var/lib/tor &

# Wait for Tor to initialize (give it 10 seconds)
echo "⏳ Waiting for Tor to establish a circuit..."
sleep 10

# Start the Streamlit app
echo "🚀 Launching ShadowPulse Dashboard..."
streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0