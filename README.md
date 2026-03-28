# GCW Point Breakdown Explorer

This repo packages your point breakdown CSV into a small Streamlit app so you can explore the stats that matter most: total points by reason, top reasons by faction or planet, timeline trends, and the highest-value source events.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud

1. Create a GitHub repo and push this folder.
2. In Streamlit Cloud, create a new app from that repo.
3. Set the main file path to `app.py`.

The app includes the current CSV in `data/gcw_points.csv`, and you can also upload a replacement CSV from the sidebar. It intentionally downplays `multiplier`, `regionName`, and the mostly-unique `source` field except where `source` helps surface standout events.
