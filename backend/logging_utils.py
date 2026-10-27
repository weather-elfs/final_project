"""KST 로그 시각과 인증정보를 제거한 수집 진단 JSON."""

import json
import logging
import math
import os
import re
from datetime import date, datetime
from urllib.parse import quote, quote_plus
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SECRET_NAMES = ("KMA_AUTH_KEY", "KMA_API_KEY", "AIRKOREA_API_KEY", "DATA_API_KEY")
SECRET_FIELD = re.compile(r"key|token|password|authorization|cookie|secret", re.I)


class KstFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, KST).strftime(
            datefmt or "%Y%m%d %H%M%S"
        )


def configure_logging():
    """Uvicorn 접근·오류 로그와 수집기 로그에 동일한 KST 시각을 붙인다."""
    logging.basicConfig(level=logging.INFO)
    formatter = KstFormatter("%(asctime)s %(levelname)s: %(message)s")
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(formatter)


def safe_log_value(value):
    """JSON으로 출력 가능한 값으로 바꾸고 키·인증 문자열을 제거한다."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SECRET_FIELD.search(key) else safe_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_log_value(item) for item in value]
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=KST) if value.tzinfo is None else value
        ).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        for name in SECRET_NAMES:
            secret = os.getenv(name)
            if secret:
                for encoded in (secret, quote(secret, safe=""), quote_plus(secret)):
                    value = value.replace(encoded, "[REDACTED]")
        return re.sub(
            r"(?i)([?&](?:servicekey|authkey|api_key|token|password)=)[^&#\s]+",
            r"\1[REDACTED]",
            value,
        )
    return value


def log_json(event, **details):
    logging.getLogger("uvicorn.error").warning(
        "%s %s",
        event,
        json.dumps(safe_log_value(details), ensure_ascii=False, allow_nan=False),
    )


def response_snapshot(document, source):
    """누락 진단에 필요한 원천 응답 필드만 보관한다. 전체 응답은 기록하지 않는다."""
    if not isinstance(document, dict):
        return {"response_type": type(document).__name__}
    response = document.get("response", document)
    if not isinstance(response, dict):
        return {"response_type": type(response).__name__}
    body = response.get("body") or {}
    items = (body.get("items") or []) if isinstance(body, dict) else []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return {
            "header": safe_log_value(response.get("header")),
            "items_type": type(items).__name__,
        }
    fields = {
        "AIRKOREA": (
            "dataTime",
            "pm25Value",
            "pm10Value",
            "pm25Flag",
            "pm10Flag",
            "so2Value",
            "coValue",
            "o3Value",
            "no2Value",
        ),
        "AIRKOREA_FORECAST": ("dataTime", "informData", "informCode", "informGrade"),
        "KMA_FORECAST": (
            "baseDate",
            "baseTime",
            "fcstDate",
            "fcstTime",
            "category",
            "fcstValue",
            "nx",
            "ny",
        ),
        "TIDE_OBSERVATORY": (
            "obsrvnDt",
            "obsvtrNm",
            "wtem",
            "slntQty",
            "artmp",
            "atmpr",
            "wspd",
            "wndrct",
            "maxMmntWspd",
        ),
    }.get(source, ())
    limit = 100 if source.endswith("FORECAST") else 3
    return safe_log_value(
        {
            "header": response.get("header"),
            "item_count": len(items),
            "sample_limit": limit,
            "items": [
                {key: item.get(key) for key in fields}
                for item in items[:limit]
                if isinstance(item, dict)
            ],
        }
    )
