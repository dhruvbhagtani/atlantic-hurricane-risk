#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/raw/geography
wget -nc --timeout=30 --tries=2 -P data/raw/geography \
  'https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip'
python -m zipfile -e data/raw/geography/ne_10m_land.zip data/raw/geography/ne_10m_land
