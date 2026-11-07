"""文件日志：data/logs/app.log（业务事件）+ access.log（每请求一行）。

RotatingFileHandler 5MB×5；UTC 时间戳；竖线分隔便于 grep。
app.log 行格式：时间|级别|类别|操作者|详情
access.log 行格式：时间|INFO|方法|路径|状态|耗时|IP|UA
"""
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import settings

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

app_logger = logging.getLogger("pw.app")
access_logger = logging.getLogger("pw.access")
_configured = False


def log_dir() -> Path:
    p = Path(settings.log_root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _utc_converter(*args):
    return time.gmtime()


def setup_file_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    for logger, fname in ((app_logger, "app.log"), (access_logger, "access.log")):
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if logger.handlers:
            continue
        h = RotatingFileHandler(log_dir() / fname, maxBytes=_MAX_BYTES,
                                backupCount=_BACKUP_COUNT, encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s|%(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
        fmt.converter = _utc_converter
        h.setFormatter(fmt)
        logger.addHandler(h)


def log_event(category: str, detail: str, actor: str = "-", level: str = "info") -> None:
    """业务事件打点。detail 内不得含凭据/明文邮箱等敏感值。"""
    getattr(app_logger, level, app_logger.info)(f"{category}|{actor}|{detail}")
