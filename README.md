# Route Scouter

Search for places along your route using KML or GPX files.

## Quick Start

1. **Clone and install:**
   ```bash
   git clone <repo-url>
   cd route-scouter
   pip install -r requirements.txt
   ```

2. **Set up your API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Google API key
   ```

3. **Run:**
   ```bash
   streamlit run app.py
   # Or use: ./run.sh
   ```

## Getting a Google API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **Places API**
4. Create an API key under Credentials
5. Paste it in your `.env` file

## Usage

1. Upload a KML or GPX route file
2. Enter what you're looking for (e.g., "coffee shops", "bars", "restaurants")
3. Adjust filters as needed
4. Click **Search**

The map will show your route and all matching places. Results include ratings, prices, and distance from your route.

## Features

- Upload KML or GPX route files
- Search along route with Google Places API
- Filter by rating, price, distance, and open hours
- Interactive map with route and results
- Export results to table view

## Requirements

- Python 3.8+
- Google Places API key (free tier available)
- KML or GPX file with your route
