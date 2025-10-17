#!/usr/bin/env python3
import json, subprocess, sys, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPUTE = ROOT / "tools" / "compute_score.py"
WEIGHTS = ROOT / "tools" / "weights.json"

REGIONS = ["taipei","newtaipei","taoyuan","taichung","tainan","kaohsiung","gta"]
SCENARIOS = ["day-clear","night-clear","day-rain","night-rain"]

def run_compute(src, dst, scenario):
  dst.parent.mkdir(parents=True, exist_ok=True)
  args = [sys.executable, str(COMPUTE), str(src), "-o", str(dst), "--sigmoid", "--weights", str(WEIGHTS), "--scenario", scenario]
  subprocess.run(args, check=True)

def main():
  generated = []
  for region in REGIONS:
    for scen in SCENARIOS:
      src = ROOT / "data" / "raw" / region / f"{scen}.json"
      if not src.exists():
        print(f"[skip] missing raw: {src}")
        continue
      with open(src, "r", encoding="utf-8") as f:
        raw = json.load(f)
      raw.setdefault("context", {})
      raw["context"]["scenario"] = scen
      with open(src, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

      out = ROOT / "data" / region / f"{scen}.json"
      run_compute(src, out, scen)
      generated.append(str(out.relative_to(ROOT)))

  idx = {"regions": REGIONS, "scenarios": SCENARIOS, "updatedAt": datetime.datetime.utcnow().isoformat()+"Z"}
  (ROOT / "data").mkdir(exist_ok=True)
  with open(ROOT / "data" / "index.json", "w", encoding="utf-8") as f:
    json.dump(idx, f, ensure_ascii=False, indent=2)

  print("Generated files:", *generated, sep="\n- ")

if __name__ == "__main__":
  main()
