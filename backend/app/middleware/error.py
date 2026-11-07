"""错误处理中间件/异常处理器注册。"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..core.errors import AppException, ErrorCode, fail


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppException)
    async def _app_exc(_: Request, exc: AppException):
        return JSONResponse(status_code=exc.http_status,
                            content=fail(exc.code, exc.message, exc.data))

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"][1:]), "msg": e["msg"]}
                  for e in exc.errors()]
        return JSONResponse(status_code=422,
                            content=fail(ErrorCode.VALIDATION, "校验失败", {"fields": fields}))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):  # pragma: no cover
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL, "服务器内部错误"))
