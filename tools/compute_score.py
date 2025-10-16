#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UGPS 計分器：把 components -> score(0~1)，或沿用既有 score。
用法：
  python tools/compute_score.py data/ugps_raw.json -o data/ugps.json --sigmoid
"""
import json, math, argparse, statistics
from copy import deepcopy

# ======== 預設權重 ========
GROUP_W = dict(pull=0.35, cover=0.30, recency=0.25, friction=0.10)  # friction 之後會用 (1-F)
INTRA_W = {
    "pull":   {"service_proximity":0.45, "transit_hub":0.35, "late_night_econ":0.20},
    "cover":  {"overhead_area":0.45, "recessed_edges":0.35, "lighting_mid":0.20},
    "friction":{"patrol_density":0.60, "cctv_density":0.40},
    "recency":{"reports_7d":0.45, "outreach_hits_14d":0.35, "night_flow_delta":0.20},
}

COUNT_LIKE = {"reports_7d", "outreach_hits_14d", "night_flow_delta"}  # 會先 log1p

def winsor_min_max(values, p_low=0.05, p_high=0.95):
    if not values:
        return (0.0, 1.0)
    vs = sorted(values)
    lo = vs[int(round((len(vs)-1)*p_low))]
    hi = vs[int(round((len(vs)-1)*p_high))]
    if hi <= lo: hi = lo + 1e-6
    return lo, hi

def normalize_series(vals, count_like=False):
    # log1p for count-like first
    arr = [ (math.log1p(v) if count_like else v) for v in vals ]
    lo, hi = winsor_min_max(arr, 0.05, 0.95)
    out = []
    for v in arr:
        vv = min(max(v, lo), hi)
        out.append( (vv - lo) / (hi - lo) if hi > lo else 0.0 )
    return out

def sigmoid(x, alpha=5.0, mu=0.5):
    z = alpha*(x - mu)
    return 1.0/(1.0 + math.exp(-z))

def weighted_mean(pairs):
    num, den = 0.0, 0.0
    for v, w in pairs:
        if v is None or w is None: continue
        num += v*w; den += w
    return (num/den) if den>0 else None

def calc_group_score(rows, group, keys):
    # 收集該組所有子項，跑標準化
    cols = {k:[] for k in keys}
    for r in rows:
        comp = (((r.get("components") or {}).get(group)) or {})
        for k in keys:
            v = comp.get(k, None)
            if v is None:
                cols[k].append(None)
            else:
                cols[k].append(float(v))

    # 對每一子項做 normalize（計數項先 log1p）
    norms = {}
    for k, series in cols.items():
        raw = [x for x in series if x is not None]
        if raw:
            normed = normalize_series(raw, count_like=(k in COUNT_LIKE))
            it = iter(normed)
            norms[k] = [ (next(it) if v is not None else None) for v in series ]
        else:
            norms[k] = [ None for _ in series ]

    # 對每筆資料，計算組內加權平均
    result = []
    for i in range(len(rows)):
        pairs = []
        for k, w in INTRA_W[group].items():
            pairs.append(( norms[k][i], w ))
        result.append( weighted_mean(pairs) )
    return result  # 0~1 或 None

def ensure_components_stub(r):
    # 若沒有 components，給空殼，讓流程可運行
    if "components" not in r or r["components"] is None:
        r["components"] = {"pull":{}, "cover":{}, "friction":{}, "recency":{}}
    else:
        for g in ["pull","cover","friction","recency"]:
            r["components"].setdefault(g, {})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="輸入 JSON（可只有 score，也可含 components）")
    ap.add_argument("-o","--output", default=None, help="輸出 JSON（預設覆寫 input）")
    ap.add_argument("--sigmoid", action="store_true", help="啟用 S 型壓縮（讓 0.6~0.8 更可分）")
    ap.add_argument("--alpha", type=float, default=5.0, help="S 型斜率（default=5）")
    ap.add_argument("--mu", type=float, default=0.5, help="S 型中心（default=0.5）")
    args = ap.parse_args()

    with open(args.input,"r",encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("grid", [])
    if not rows:
        print("grid 為空，無需處理。")
        return

    # 確保每列都有 components 殼
    for r in rows: ensure_components_stub(r)

    # 若全部都沒有 components 值，直接沿用既有 score
    has_any_component = any(
        any(((r["components"].get(g) or {}).get(k) is not None)
            for k in INTRA_W[g].keys())
        for g in INTRA_W.keys() for r in rows
    )

    if not has_any_component:
        print("未偵測到 components，沿用原始 score（若無 score，補 0）。")
        for r in rows:
            r["score"] = float(r.get("score", 0.0) or 0.0)
        out = data
    else:
        # 逐組計算 0~1 分數
        keys = {g:list(INTRA_W[g].keys()) for g in INTRA_W.keys()}
        P = calc_group_score(rows, "pull",    keys["pull"])
        C = calc_group_score(rows, "cover",   keys["cover"])
        F = calc_group_score(rows, "friction",keys["friction"])
        R = calc_group_score(rows, "recency", keys["recency"])

        # 組合總分
        scores0 = []
        for i, r in enumerate(rows):
            # 缺值以組平均替補（保守）
            def safe(v, fallback):
                return v if (v is not None) else fallback
            Pm = safe(P[i], statistics.fmean([x for x in P if x is not None]) if any(x is not None for x in P) else 0.0)
            Cm = safe(C[i], statistics.fmean([x for x in C if x is not None]) if any(x is not None for x in C) else 0.0)
            Fm = safe(F[i], statistics.fmean([x for x in F if x is not None]) if any(x is not None for x in F) else 0.5)
            Rm = safe(R[i], statistics.fmean([x for x in R if x is not None]) if any(x is not None for x in R) else 0.0)

            S0 = (GROUP_W["pull"]*Pm +
                  GROUP_W["cover"]*Cm +
                  GROUP_W["recency"]*Rm +
                  GROUP_W["friction"]*(1.0 - Fm))
            scores0.append(S0)

        # optional S 型壓縮
        if args.sigmoid:
            mu = args.mu if args.mu is not None else (statistics.median(scores0) if scores0 else 0.5)
            alpha = args.alpha
            scores = [ sigmoid(s, alpha=alpha, mu=mu) for s in scores0 ]
        else:
            scores = scores0

        # 更新 rows
        out = deepcopy(data)
        for r, s in zip(out["grid"], scores):
            r["score"] = max(0.0, min(1.0, float(s)))

        # 簡易 confidence（可自行調整）
        # freshness: 目前沒有資料時間戳，給 1.0；coverage：components 非空比例
        for r in out["grid"]:
            comp = r.get("components", {})
            total = sum(len(v or {}) for v in comp.values())
            filled = sum(1 for g in comp.values() for _k,_v in (g or {}).items() if _v is not None)
            coverage = (filled/total) if total>0 else 0.0
            r["confidence"] = round(0.7*1.0 + 0.3*coverage, 3)  # 先以 1.0 當 freshness 佔 70%

    # 輸出
    outpath = args.output or args.input
    with open(outpath,"w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"寫出：{outpath}")
    # 簡要摘要
    scs = [r.get("score",0.0) for r in out.get("grid",[])]
    if scs:
        print(f"score min/med/max = {min(scs):.2f}/{statistics.median(scs):.2f}/{max(scs):.2f}")
