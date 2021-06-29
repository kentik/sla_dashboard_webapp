from datetime import datetime, timezone


def utc_to_localtime(time: datetime) -> datetime:
    return time.astimezone(tz=None)
