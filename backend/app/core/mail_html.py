"""Markdown → 邮件 HTML。

邮件客户端不认外部 CSS、flex/grid 也不稳，所以这里只出保守排版：
620px 卡片 + 内联样式兜底 + 一段极简 <style>（标题/段落/代码/引用/表格）。
底色走浅色（白卡 + 浅灰背景）—— 深色邮件在 Gmail/Outlook 里会被各自的暗色模式二次反色，
观感不可控，浅色反而稳定。
"""
from markdown_it import MarkdownIt

# html=False：正文里的原始 HTML 一律转义，邮件里绝不执行作者写的标签
_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table").enable("strikethrough")

ACCENT = "#0d9488"       # 浅底上用深一档的主色，保证对比度
INK = "#0f172a"
INK2 = "#475569"
INK3 = "#94a3b8"
BORDER = "#e2e8f0"

_STYLE = f"""
body{{margin:0;padding:24px 12px;background:#f6f7f8;
  font:15px/1.75 -apple-system,"Segoe UI","PingFang SC","Noto Sans SC",sans-serif;color:{INK};}}
.wrap{{max-width:640px;margin:0 auto;background:#fff;border:1px solid {BORDER};}}
.head{{padding:20px 24px 0;}}
.kicker{{font:600 10px/1 ui-monospace,Consolas,monospace;letter-spacing:.2em;
  text-transform:uppercase;color:{ACCENT};}}
.title{{margin:10px 0 6px;font-size:19px;line-height:1.45;font-weight:600;color:{INK};}}
.meta{{font:12px/1.6 ui-monospace,Consolas,monospace;color:{INK3};}}
.rule{{height:1px;background:{BORDER};margin:16px 24px;}}
.body{{padding:0 24px 4px;}}
.body h1,.body h2,.body h3{{margin:20px 0 8px;line-height:1.4;color:{INK};}}
.body h1{{font-size:18px;}} .body h2{{font-size:16px;}} .body h3{{font-size:15px;}}
.body p{{margin:10px 0;}}
.body a{{color:{ACCENT};text-decoration:none;border-bottom:1px solid {BORDER};}}
.body ul,.body ol{{margin:10px 0;padding-left:22px;}}
.body li{{margin:4px 0;}}
.body code{{font:12.5px/1.5 ui-monospace,Consolas,monospace;background:#f1f5f9;
  border:1px solid {BORDER};padding:1px 4px;}}
.body pre{{background:#f8fafc;border:1px solid {BORDER};padding:12px 14px;overflow:auto;}}
.body pre code{{background:none;border:0;padding:0;}}
.body blockquote{{margin:12px 0;padding:2px 0 2px 14px;border-left:2px solid {ACCENT};color:{INK2};}}
.body hr{{border:0;border-top:1px solid {BORDER};margin:18px 0;}}
.body table{{border-collapse:collapse;margin:12px 0;font-size:13.5px;}}
.body th,.body td{{border:1px solid {BORDER};padding:6px 10px;text-align:left;}}
.body th{{background:#f8fafc;font-weight:600;}}
.foot{{padding:14px 24px 20px;font:11px/1.7 ui-monospace,Consolas,monospace;color:{INK3};}}
"""


def render_body(markdown_text: str) -> str:
    """只渲染正文片段（不含外壳）。空正文返回空串。"""
    return _md.render(markdown_text or "").strip()


def document(*, kicker: str, title: str, meta: str, body_md: str,
             foot: str = "", foot_html: str = "") -> str:
    """整封邮件的 HTML：眉题 + 标题 + 元信息行 + Markdown 正文 + 页脚。

    foot 走纯文本（会被转义），foot_html 用于放链接这类必须带标记的页脚。
    """
    body = render_body(body_md)
    foot_part = foot_html or _escape(foot)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{_STYLE}</style></head>"
        '<body><div class="wrap">'
        f'<div class="head"><div class="kicker">{_escape(kicker)}</div>'
        f'<div class="title">{_escape(title)}</div>'
        f'<div class="meta">{_escape(meta)}</div></div>'
        '<div class="rule"></div>'
        f'<div class="body">{body}</div>'
        + (f'<div class="rule"></div><div class="foot">{foot_part}</div>' if foot_part else "")
        + "</div></body></html>"
    )


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
