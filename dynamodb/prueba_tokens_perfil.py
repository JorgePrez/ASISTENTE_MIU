#!/usr/bin/env python3
"""
bedrock_tokens_cloudwatch.py

Consulta CloudWatch Metrics de Amazon Bedrock (InputTokenCount/OutputTokenCount)
filtrando por ModelId y un rango de fechas, y devuelve los totales.

Requisitos:
  pip install boto3
Uso:
  python bedrock_tokens_cloudwatch.py --model-id n5jvsjttrqct --region us-east-1
  python bedrock_tokens_cloudwatch.py --model-id n5jvsjttrqct --start 2026-01-01T00:00:00Z --end 2026-01-13T23:59:59Z
"""

import argparse
import datetime as dt
import json
from typing import Tuple, Optional

import boto3


NAMESPACE = "AWS/Bedrock"
METRIC_INPUT = "InputTokenCount"
METRIC_OUTPUT = "OutputTokenCount"
DIM_NAME = "ModelId"


def parse_iso_z(s: str) -> dt.datetime:
    """
    Parse ISO-8601 timestamps like:
      2026-01-01T00:00:00Z
      2026-01-01T00:00:00+00:00
    Returns timezone-aware datetime (UTC).
    """
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        # assume UTC if no tz provided
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def month_range_utc(now: Optional[dt.datetime] = None) -> Tuple[dt.datetime, dt.datetime]:
    now = now or dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    end = now
    return start, end


def sum_metric(
    cw,
    region: str,
    model_id: str,
    metric_name: str,
    start: dt.datetime,
    end: dt.datetime,
    period_seconds: int,
) -> int:
    """
    Use GetMetricData (paged) and sum all returned Values.
    """
    query = [
        {
            "Id": "m1",
            "MetricStat": {
                "Metric": {
                    "Namespace": NAMESPACE,
                    "MetricName": metric_name,
                    "Dimensions": [{"Name": DIM_NAME, "Value": model_id}],
                },
                "Period": period_seconds,
                "Stat": "Sum",
            },
            "ReturnData": True,
        }
    ]

    total = 0
    next_token = None

    while True:
        kwargs = {
            "MetricDataQueries": query,
            "StartTime": start,
            "EndTime": end,
            "ScanBy": "TimestampAscending",
        }
        if next_token:
            kwargs["NextToken"] = next_token

        resp = cw.get_metric_data(**kwargs)
        results = resp.get("MetricDataResults", [])
        if results:
            vals = results[0].get("Values", [])
            total += int(round(sum(vals)))

        next_token = resp.get("NextToken")
        if not next_token:
            break

    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="us-east-1", help="Región donde están las métricas (ej: us-east-1)")
    ap.add_argument("--model-id", required=True, help="ModelId que aparece en CloudWatch (ej: n5jvsjttrqct)")
    ap.add_argument("--start", help="Inicio ISO (UTC) ej: 2026-01-01T00:00:00Z. Si no se da: 1er día del mes.")
    ap.add_argument("--end", help="Fin ISO (UTC) ej: 2026-01-13T23:59:59Z. Si no se da: ahora.")
    ap.add_argument(
        "--period",
        type=int,
        default=86400,
        help="Period en segundos para agregación. Recomendado 86400 (1 día) para rangos largos.",
    )
    args = ap.parse_args()

    if args.start and args.end:
        start = parse_iso_z(args.start)
        end = parse_iso_z(args.end)
    else:
        start, end = month_range_utc()

    if end <= start:
        raise SystemExit("Error: end debe ser mayor que start")

    cw = boto3.client("cloudwatch", region_name=args.region)

    input_total = sum_metric(
        cw=cw,
        region=args.region,
        model_id=args.model_id,
        metric_name=METRIC_INPUT,
        start=start,
        end=end,
        period_seconds=args.period,
    )
    output_total = sum_metric(
        cw=cw,
        region=args.region,
        model_id=args.model_id,
        metric_name=METRIC_OUTPUT,
        start=start,
        end=end,
        period_seconds=args.period,
    )

    out = {
        "namespace": NAMESPACE,
        "dimension": {DIM_NAME: args.model_id},
        "range_utc": {"start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z")},
        "period_seconds": args.period,
        "input_tokens": input_total,
        "output_tokens": output_total,
        "total_tokens": input_total + output_total,
    }

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
