# ugps-demo
Unsheltered Gathering Potential Score
---

## 評分與權重（Scoring & Weighting）

UGPS 的分數 `score ∈ [0,1]`，代表「此網格（cell）出現街頭停留（unsheltered gathering）之**相對潛勢**」。
分數可由兩種來源取得：

1. **直供分數（passthrough）**：`data/ugps_raw.json` 已含 `score`，工具會直接沿用（不重新計算）。
2. **特徵合成（components → score）**：`data/ugps_raw.json` 提供各群組/子項 **components**，工具以權重加總後輸出 `score`。

> 工具：`tools/compute_score.py`
> 指令：`python tools/compute_score.py data/ugps_raw.json -o data/ugps.json --sigmoid`

---

### 1. 整體流程（Overview）

```
原始資料 (ugps_raw.json)
  ├─ 有 score            → 直接沿用（passthrough）
  └─ 有 components       → 正規化/剪尾/對數變換 → 權重加總 → (可選)Sigmoid → score
輸出 (ugps.json) → 前端載入顯示（點位/熱度圖/Top-3）
```

---

### 2. 分數合成公式（Formula）

若提供 `components`，每個 cell 的分數為

[
\text{score} = \sigma\Big(
w_{pull} \cdot \text{Pull} +
w_{cover} \cdot \text{Cover} +
w_{recency} \cdot \text{Recency} +
w_{friction} \cdot (1 - \text{Friction})
\Big)
]

* ( w_{*} )：群組權重（工具內會正規化為和為 1）
* 群組值為其子項加權和（同樣會正規化）

[
\text{Pull} = \sum_i \alpha_i^{(pull)} \cdot x_i^{(pull)}, \quad
\text{Cover} = \sum_i \alpha_i^{(cover)} \cdot x_i^{(cover)}, \dots
]

* ( \sigma(\cdot) )：可選的 Sigmoid（`--sigmoid`），用來壓抑極端值，拉出中段可讀性。
* **Friction 採反向**（越大越不利，因此用 ( 1-\text{Friction} )）。

---

### 3. 預設群組與子項（Default Weights）

> 你可在 `tools/compute_score.py` 最上方調整，修改後重新產出 `ugps.json` 即可。

**群組權重 `GROUP_W`（可調）**

```python
GROUP_W = dict(
  pull=0.35,
  cover=0.30,
  recency=0.25,
  friction=0.10,  # friction 以 (1 - 值) 納入
)
```

**群組內子項 `INTRA_W`（可調；工具會正規化）**

```python
INTRA_W = {
  "pull": {
    "service_proximity": 0.45,  # 服務/資源的臨近程度
    "transit_hub":       0.35,  # 轉運/車站權重
    "late_night_econ":   0.20   # 深夜經濟活躍度
  },
  "cover": {
    "overhead_area":     0.45,  # 可遮蔽空間（騎樓/橋下…）
    "recessed_edges":    0.35,  # 退縮邊界、凹洞
    "lighting_mid":      0.20   # 照明中度（過暗或過亮皆不利停留）
  },
  "friction": {
    "patrol_density":    0.60,  # 巡邏/管理密度（越高越不利）
    "cctv_density":      0.40   # CCTV 密度（越高越不利）
  },
  "recency": {
    "reports_7d":        0.45,  # 近 7 天通報
    "outreach_hits_14d": 0.35,  # 近 14 天外展接觸
    "night_flow_delta":  0.20   # 夜間人流變化
  }
}
```

---

### 4. 特徵前處理（Normalization & Cleaning）

為降低噪音與單位差異，工具在合成前對每個**子項**做：

1. **Winsorize 剪尾**（缺省 p_low=0.05, p_high=0.95）
   把極端值「截斷」到分位點，避免少數異常拖壞尺度。
2. **log1p**（只對「計數型」特徵）
   針對 ({ reports_7d, outreach_hits_14d, night_flow_delta }) 等「越多越可能」的事件型特徵先做 `log1p(x)`，再正規化。
3. **Min–Max 正規化到 [0,1]**
   讓所有子項在同一尺度上權重可比。
4. **Friction 反向**
   最終是以 (1 - \text{friction}) 進入總分（阻力越高越不利）。

> 這些預設都寫在 `compute_score.py`，如需改分位數或是否 log1p，可在檔案開頭調整。

---

### 5. 指令用法（CLI）

**基本：**

```bash
python tools/compute_score.py data/ugps_raw.json -o data/ugps.json
```

**加上 Sigmoid 壓縮（建議）：**

```bash
python tools/compute_score.py data/ugps_raw.json -o data/ugps.json --sigmoid
```

**只沿用既有 score（raw 就有 score；你現在的情境）：**
同上指令，工具會偵測沒有 `components`，採 passthrough 輸出。

---

### 6. 調參建議（How to Tune）

1. **先動群組，再動子項**
   先用 `GROUP_W` 控中大方向（例如把 `recency` 從 0.25 提到 0.35，看 Top-3/熱度是否合理），再微調 `INTRA_W`。
2. **一次只動 1–2 個參數**
   每次調整記錄前後差異，太多同時變動會難以解讀效果。
3. **保留 Sigmoid，但注意強度**
   有助中段分辨率；若整體太扁或太尖，可改為不加 `--sigmoid` 或改工具內的壓縮方式。
4. **多期比較**
   用歷史數據驗證：Top-3 是否與外展體感/事件記錄一致？是否「可解釋」。

---

### 7. 範例資料格式

**只含 score（passthrough）**

```json
{
  "version": "v0.0.1",
  "generatedAt": "2025-10-16T00:00:00Z",
  "context": { "timezone": "Asia/Taipei", "scenario": "day-clear" },
  "grid": [
    { "id": "A12", "lat": 25.0478, "lon": 121.5170, "score": 0.53 },
    { "id": "B07", "lat": 25.0486, "lon": 121.5151, "score": 0.41 },
    { "id": "C19", "lat": 25.0459, "lon": 121.5163, "score": 0.62 }
  ]
}
```

**含 components（工具會計算 score）**

```json
{
  "grid": [
    {
      "id": "A12", "lat": 25.0478, "lon": 121.5170,
      "components": {
        "pull":    { "service_proximity": 0.45, "transit_hub": 0.35, "late_night_econ": 0.20 },
        "cover":   { "overhead_area": 0.45, "recessed_edges": 0.35, "lighting_mid": 0.20 },
        "friction":{ "patrol_density": 0.60, "cctv_density": 0.40 },
        "recency": { "reports_7d": 10, "outreach_hits_14d": 5, "night_flow_delta": 3 }
      }
    }
  ]
}
```

---

### 8. 品質檢查（Sanity Checks）

* **Top-3 是否合理**：結果與外展/熱點體感相近？是否受單一特徵主宰？
* **地圖層級視覺**：縮放不同層級，熱圖是否過度蔓延或過淡（可交互調整前端半徑與這裡的 Sigmoid/權重）。
* **數值範圍**：`score` 應落在 `[0,1]`；若都接近 0 或 1，考慮取消/調整 Sigmoid 或擴大群組對比。

---

### 9. 常見問題（Troubleshooting）

* **「我只有 `score`，可不可以？」** 可以；工具會 passthrough。
* **「子項尺度差很多怎麼辦？」** 由剪尾 + 正規化處理；若仍偏斜，可調剪尾分位或加入更強的對數變換。
* **「Friction 是正向還反向？」** 是**反向**，以 (1-\text{friction}) 參與總分。
* **「熱圖太挑或太淡」**：先檢查 `score` 分佈（`data/ugps.json`），確定不是後端過度壓縮；再微調前端熱圖半徑/顏色與此處的 Sigmoid/權重。

---

### 10. 未來擴充

* 支援更多情境（白天/夜晚、晴雨、工作日/週末）對權重做**情境化配置**。
* 以 AutoML/貝氏優化等方法自動尋找權重（保留「可解釋」的限制）。
* 納入時變特徵（例如每小時流量）以**時空**方式產生 score。

---

> 若要快速上手：**不改任何權重**，直接跑
> `python tools/compute_score.py data/ugps_raw.json -o data/ugps.json --sigmoid`
> 重新整理前端即可。需要調整時，再回來改 `GROUP_W` / `INTRA_W`，重跑一次觀察效果。
