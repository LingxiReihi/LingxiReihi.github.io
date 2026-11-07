from typing import Any


class ErrorCode:
    OK = 0
    BAD_REQUEST = 40000
    UNAUTHORIZED = 40100
    BAD_CREDENTIALS = 40101
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    CONFLICT = 40900
    TOO_LARGE = 41300
    UNSUPPORTED_TYPE = 41500
    VALIDATION = 42200
    LOCKED = 42300
    RATE_LIMITED = 42900
    SERVICE_UNAVAILABLE = 50300
    INTERNAL = 50000


HTTP_BY_CODE = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.BAD_CREDENTIALS: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_TYPE: 415,
    ErrorCode.VALIDATION: 422,
    ErrorCode.LOCKED: 423,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL: 500,
}


class AppException(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.http_status = HTTP_BY_CODE.get(code, 400)
        self.message = message
        self.data = data
        super().__init__(message)


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": ErrorCode.OK, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}
