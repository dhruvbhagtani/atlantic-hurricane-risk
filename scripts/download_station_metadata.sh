#!/usr/bin/env bash
set -euo pipefail
metadata_dir=data/raw/metadata
mkdir -p "$metadata_dir"
task_tmp=$(mktemp "$metadata_dir/.homr-KVLD-XXXXXX.json")
trap 'rm -f "$task_tmp"' EXIT
wget --timeout=30 --tries=2 -O "$task_tmp" \
  'https://www.ncei.noaa.gov/access/homr/services/station/search?qid=WBAN:93845&date=all&definitions=false&phrData=true'
python - "$task_tmp" <<'PY'
import json,sys
with open(sys.argv[1]) as stream:
    data=json.load(stream)
if not data.get('stationCollection',{}).get('stations'):
    raise SystemExit('No station records in HOMR response; keep the response for investigation.')
PY
mv "$task_tmp" "$metadata_dir/homr_KVLD.json"
printf 'Saved %s\n' "$metadata_dir/homr_KVLD.json"
