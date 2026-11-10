#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/raw/global_hourly/2020 data/raw/metadata
wget -nc --timeout=30 --tries=2 -P data/raw/global_hourly/2020 \
  'https://noaa-global-hourly-pds.s3.amazonaws.com/2020/72240003937.csv'
task_tmp=$(mktemp data/raw/metadata/.homr-KLCH-XXXXXX.json)
trap 'rm -f "$task_tmp"' EXIT
wget --timeout=30 --tries=2 -O "$task_tmp" \
  'https://www.ncei.noaa.gov/access/homr/services/station/search?qid=WBAN:03937&date=all&definitions=false&phrData=true'
python - "$task_tmp" <<'PY'
import json,sys
with open(sys.argv[1]) as f:data=json.load(f)
if not data.get('stationCollection',{}).get('stations'):raise SystemExit('No station history in response')
PY
mv "$task_tmp" data/raw/metadata/homr_KLCH.json
printf 'Laura station-year data and station history downloaded.\n'
