#!/bin/bash
cd "$(dirname "$0")"
streamlit run app.py \
    --server.headless true \
    --server.address localhost \
    --browser.gatherUsageStats false
