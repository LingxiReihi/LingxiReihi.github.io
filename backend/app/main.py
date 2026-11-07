from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import admin_auth, comments as comments_api, public, seo_public
from .api.admin import admins as admins_api, announcements as announcements_api, comments as admin_comments_api, contents, logs as logs_api, media as media_api, profile as profile_api, seo_stats, site as site_api
from .core.config import settings
from .core.errors import ok
from .core.logs import setup_file_logging
from .middleware.access_track import AccessTrackMiddleware
from .middleware.error import register_error_handlers
from .middleware.request_log import RequestLogMiddleware
from .tasks.aggregate import aggregate_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    task = asyncio.create_task(aggregate_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="personal-web api", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
    setup_file_logging()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessTrackMiddleware)
    app.add_middleware(RequestLogMiddleware)
    register_error_handlers(app)

    api = "/api/v1"
    app.include_router(admin_auth.router, prefix=api)
    app.include_router(public.router, prefix=api)
    app.include_router(comments_api.router, prefix=api)
    app.include_router(admin_comments_api.router, prefix=f"{api}/admin")
    app.include_router(admins_api.router, prefix=f"{api}/admin")
    app.include_router(profile_api.router, prefix=f"{api}/admin")
    app.include_router(contents.router, prefix=f"{api}/admin")
    app.include_router(media_api.router, prefix=f"{api}/admin")
    app.include_router(site_api.tags_router, prefix=f"{api}/admin")
    app.include_router(site_api.columns_router, prefix=f"{api}/admin")
    app.include_router(site_api.settings_router, prefix=f"{api}/admin")
    app.include_router(announcements_api.router, prefix=f"{api}/admin")
    app.include_router(logs_api.router, prefix=f"{api}/admin")
    app.include_router(seo_stats.stats_router, prefix=f"{api}/admin")
    app.include_router(seo_stats.seo_router, prefix=f"{api}/admin")

    # 媒体静态直出（生产由 Caddy 接管同路径）
    app.mount("/media", StaticFiles(directory=str(settings.media_path)), name="media")

    # 根级 SEO 端点最后注册（含验证文件 catch-all）
    app.include_router(seo_public.router)

    @app.get(f"{api}/health")
    async def health():
        return ok({"status": "ok"})

    return app


app = create_app()
