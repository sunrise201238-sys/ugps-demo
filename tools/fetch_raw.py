#!/usr/bin/env python3
# (Source file generated; place into tools/)
import os, json, math, time, argparse, pathlib, requests, datetime
from typing import Dict, List, Tuple

OVERPASS = "https://overpass-api.de/api/interpreter"

AMENITY_PULL = [
  'shelter','social_facility','hospital','clinic','pharmacy','place_of_worship','public_building','toilets','drinking_water','food_bank'
]
LATE_NIGHT = [
  'convenience','fast_food','restaurant','bar','pub','kiosk','supermarket'
]
TRANSIT = {
  'railway':['station','halt','subway_entrance'],
  'public_transport':['stop_position','platform','station'],
  'highway':['bus_stop']
}

def bbox_to_str(b):
  # south, west, north, east
  return f"{b[0]},{b[1]},{b[2]},{b[3]}"

def overpass_query(q):
  for i in range(4):
    try:
      r = requests.post(OVERPASS, data={'data': q}, timeout=120)
      if r.status_code == 429:
        time.sleep(5*(i+1)); continue
      r.raise_for_status()
      return r.json()
    except Exception:
      time.sleep(5*(i+1))
  raise RuntimeError("Overpass failed")

def collect_points(bbox):
  s = bbox_to_str(bbox)
  points = { 'service':[], 'late':[], 'transit':[], 'roof':[], 'covered':[], 'police':[], 'camera':[] }

  # amenities (pull)
  q1 = (
    "[out:json][timeout:90];("
    + f'node["amenity"~"^({ "|".join(AMENITY_PULL) })$"]({s});'
    + f'way["amenity"~"^({ "|".join(AMENITY_PULL) })$"]({s});'
    + "); out center;"
  )
  j = overpass_query(q1)
  for el in j.get('elements', []):
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat and lon: points['service'].append((lat,lon))

  # late night econ
  q2 = (
    "[out:json][timeout:90];("
    + f'node["amenity"~"^({ "|".join(LATE_NIGHT) })$"]({s});'
    + f'way["amenity"~"^({ "|".join(LATE_NIGHT) })$"]({s});'
    + f'node["shop"="convenience"]({s});'
    + f'way["shop"="convenience"]({s});'
    + "); out center;"
  )
  j = overpass_query(q2)
  for el in j.get('elements', []):
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat and lon: points['late'].append((lat,lon))

  # transit
  parts = []
  for k,vals in TRANSIT.items():
    for v in vals:
      parts.append(f'node["{k}"="{v}"]({s});')
      parts.append(f'way["{k}"="{v}"]({s});')
  q3 = "[out:json][timeout:90];(" + "".join(parts) + "); out center;"
  j = overpass_query(q3)
  for el in j.get('elements', []):
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat and lon: points['transit'].append((lat,lon))

  # cover (roof/covered/tunnel/arcade)
  q4 = (
    "[out:json][timeout:90];("
    + f'way["building"="roof"]({s});'
    + f'way["covered"="yes"]({s});'
    + f'way["tunnel"="yes"]({s});'
    + f'way["arcade"="yes"]({s});'
    + "); out center;"
  )
  j = overpass_query(q4)
  for el in j.get('elements', []):
    c = el.get('tags',{})
    lat = (el.get('center') or {}).get('lat')
    lon = (el.get('center') or {}).get('lon')
    if not (lat and lon): continue
    if c.get('building')=='roof': points['roof'].append((lat,lon))
    elif c.get('covered')=='yes': points['covered'].append((lat,lon))
    else: points['covered'].append((lat,lon))

  # friction (police, cameras)
  q5 = (
    "[out:json][timeout:90];("
    + f'node["amenity"="police"]({s});'
    + f'node["man_made"="surveillance"]({s});'
    + f'way["man_made"="surveillance"]({s});'
    + "); out center;"
  )
  j = overpass_query(q5)
  for el in j.get('elements', []):
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat and lon:
      tg = (el.get('tags') or {})
      if tg.get('amenity')=='police': points['police'].append((lat,lon))
      else: points['camera'].append((lat,lon))

  return points

def grid_cells(bbox, step_m=400):
  south, west, north, east = bbox
  lat0 = (south+north)/2.0
  m_per_deg_lat = 111132.92
  m_per_deg_lon = 111412.84 * math.cos(math.radians(lat0))
  dlat = step_m / m_per_deg_lat
  dlon = step_m / m_per_deg_lon
  lat = south
  cells = []
  i = 0
  while lat < north:
    lon = west
    while lon < east:
      cells.append((i, lat + dlat/2, lon + dlon/2))
      i += 1
      lon += dlon
    lat += dlat
  return cells

def count_within(points, lat, lon, radius_m=300):
  R=6371000.0
  out = {}
  for k,pts in points.items():
    cnt = 0
    for (a,b) in pts:
      dlat = math.radians(a-lat); dlon = math.radians(b-lon)
      sa = math.sin(dlat/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(a))*math.sin(dlon/2)**2
      d = 2*R*math.asin(min(1, math.sqrt(sa)))
      if d <= radius_m:
        cnt += 1
    out[k] = cnt
  return out

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--regions", default="data/regions.json")
  ap.add_argument("--scenarios", default="day-clear,night-clear,day-rain,night-rain")
  ap.add_argument("--step_m", type=int, default=400)
  ap.add_argument("--radius_m", type=int, default=300)
  args = ap.parse_args()

  root = pathlib.Path(__file__).resolve().parents[1]
  with open(root / args.regions, "r", encoding="utf-8") as f:
    regions = json.load(f)

  for name, meta in regions.items():
    bbox = meta["bbox"]
    print(f"[fetch] {name} bbox={bbox}")
    pts = collect_points(bbox)
    cells = grid_cells(bbox, step_m=args.step_m)

    for scen in args.scenarios.split(","):
      out = {"version":"v0.0.2","generatedAt":datetime.datetime.utcnow().isoformat()+"Z",
             "context":{"timezone":meta.get("tz","UTC"),"scenario":scen},
             "grid":[]}
      for i,lat,lon in cells:
        counts = count_within(pts, lat, lon, radius_m=args.radius_m)
        comp = {
          "pull":{
            "service_proximity": counts['service'],
            "transit_hub": counts['transit'],
            "late_night_econ": counts['late']
          },
          "cover":{
            "overhead_area": counts['roof'],
            "recessed_edges": counts['covered'],
            "lighting_mid": 0
          },
          "friction":{
            "patrol_density": counts['police'],
            "cctv_density": counts['camera']
          },
          "recency":{
            "reports_7d": 0, "outreach_hits_14d": 0, "night_flow_delta": 0 if 'day' in scen else counts['late']
          }
        }
        out["grid"].append({"id": f"C{i}", "lat": lat, "lon": lon, "components": comp})
      dst = root / "data" / "raw" / name
      dst.mkdir(parents=True, exist_ok=True)
      with open(dst / f"{scen}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
      print(f"[write] data/raw/{name}/{scen}.json  cells={len(cells)}")

if __name__ == "__main__":
  main()
