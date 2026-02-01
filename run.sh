#!/bin/bash
cd "$(dirname "$0")"
/Users/alechudson/Library/Python/3.9/bin/streamlit run app.py \
    --server.headless true \
    --server.address localhost \
    --browser.gatherUsageStats false
