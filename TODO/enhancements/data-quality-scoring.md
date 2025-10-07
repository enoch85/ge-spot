# Data Quality Scoring

Score data quality (completeness, consistency, freshness).

## Why

Choose best source automatically.

## What to Create

`custom_components/ge_spot/quality/scorer.py`

## Should Calculate

- Completeness: Are all 96 intervals present?
- Consistency: Any unrealistic price spikes?
- Timeliness: How fresh is the data?
- Reliability: Historical success rate

## Add to Sensors

- `data_quality_score` attribute (0-100)
- Breakdown by dimension
