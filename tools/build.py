#!/usr/bin/env python3
import os, json, subprocess, sys, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
compute = ROOT / "compute_score.py"

REGIONS = {
  "taipei": {"center": [25.0478, 121.5170], "tz":"Asia/Taipei"},
  "newtaipei": {"center": [25.0169, 121.4628], "tz":"Asia/Taipei"},
  "taoyuan": {"center": [24.9937, 121.2969], "tz":"Asia/Taipei"},
  "taichung": {"center": [24.1477, 120.6736], "tz":"Asia/Taipei"},
  "tainan": {"center": [22.9999, 120.2269], "tz":"Asia/Taipei"},
  "kaohsiung": {"center": [22.6273, 120.3014], "tz":"Asia/Taipei"},
  "gta": {"center": [35.6762, 139.6503], "tz":"Asia/Tokyo"}
}
SCENARIOS = ["day-clear","night-clear","day-rain","night-rain"]

def ensure_dirs(p): p.mkdir(parents=True, exist_ok=True)

def run_compute(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    # call the compute script (uses only stdlib)
    subprocess.run([sys.executable, str(compute), str(src), "-o", str(dst), "--sigmoid"], check=True)

def main():
    root = ROOT
    generated = []
    for region, meta in REGIONS.items():
        for scen in SCENARIOS:
            src = root / "data" / "raw" / region / f"{scen}.json"
            if not src.exists():
                print(f"[skip] missing raw: {src}")
                continue
            # ensure context->scenario and timezone
            with open(src, "r", encoding="utf-8") as f:
                raw = json.load(f)
            raw.setdefault("context", {})
            raw["context"]["scenario"] = scen
            raw["context"]["timezone"] = meta.get("tz", "UTC")
            raw["generatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
            with open(src, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)

            out = root / "data" / region / f"{scen}.json"
            run_compute(src, out)
            generated.append(str(out.relative_to(root)))
    # also write an index for the UI
    idx = {"regions": REGIONS, "scenarios": SCENARIOS, "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"}
    with open(root / "data" / "index.json", "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    print("Generated files:", *generated, sep="\n- ")

if __name__ == "__main__":
    main()
