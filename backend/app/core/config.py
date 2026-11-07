from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    jwt_secret: str = "dev-secret-change-me"
    media_root: str = "./data/media"
    log_root: str = "./data/logs"
    cors_origins: str = "http://localhost:5173"
    site_url: str = "http://localhost:5173"

    access_token_minutes: int = 120
    refresh_token_days: int = 7

    # Baidu SEO (docs/backend-architecture.md §10.1)
    baidu_push_api: str = ""          # 未配置 => 只记 pending_push
    seo_push_enabled: bool = False
    rebuild_script: str = ""          # 服务器本机重建脚本，未配置 => skipped
    rebuild_request_file: str = ""    # Docker 模式：写重建请求文件，由宿主机 watcher 拉起构建
    rebuild_merge_seconds: float = 10.0  # 发布合并窗口（测试置 0）
    rebuild_internal_token: str = ""  # rebuild-callback 预留（本机构建默认不用）
    baidu_verify_name: str = ""       # 如 baidu_verify_codeva-xxxx.html
    baidu_verify_content: str = ""    # 验证文件正文

    # 邮件通道：同服务器 personal-mail 的外部发信 API。后台「站点设置 → 邮件通道」优先，
    # 这里只作兜底（站点设置没填时生效），线上一般只留 url 默认值 + 空 key
    mail_api_url: str = "http://mail:8000/api/external/send"
    mail_api_key: str = ""            # 空 => 忘记密码不可用（明确报「通道未配置」，不静默）
    mail_override_to: str = ""        # 测试用：非空时把重置邮件一律改投该地址

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def media_path(self) -> Path:
        p = Path(self.media_root)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
