import os
import re
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import bcrypt
import bleach
import frontmatter
import markdown
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

BASE_DIR = Path(__file__).parent
BLOG_DIR = BASE_DIR / "content" / "blog"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "arseniy")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").encode()

app = FastAPI(title="arseniy")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# ── Rate limiting ─────────────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 5        # max failed attempts
_RATE_WINDOW = 15 * 60 # window in seconds

def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW]
    return len(_login_attempts[ip]) >= _RATE_LIMIT

def _record_failure(ip: str) -> None:
    _login_attempts[ip].append(time.time())
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ── Projects ──────────────────────────────────────────────────
PROJECTS = [
    {
        "title": "my website",
        "description": "This site. Built with FastAPI, Jinja2 and vanilla CSS.",
        "tags": ["fastapi", "jinja2", "python"],
        "github": "https://github.com/Arseniy404/website",
        "demo": "/",
    },
]

# ── Helpers ───────────────────────────────────────────────────
def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def load_posts() -> list[dict]:
    posts = []
    for path in BLOG_DIR.glob("*.md"):
        post = frontmatter.load(path)
        if post.get("draft", False):
            continue
        posts.append({
            "slug": path.stem,
            "title": post["title"],
            "description": post.get("description", ""),
            "date": parse_date(post["date"]),
            "body": post.content,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def load_all_posts() -> list[dict]:
    posts = []
    for path in BLOG_DIR.glob("*.md"):
        post = frontmatter.load(path)
        posts.append({
            "slug": path.stem,
            "title": post["title"],
            "description": post.get("description", ""),
            "date": parse_date(post["date"]),
            "draft": post.get("draft", False),
            "body": post.content,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


_ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "em", "del", "code", "pre", "blockquote",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "th": ["align"],
    "td": ["align"],
}

def render_markdown(text: str) -> str:
    html = markdown.markdown(text, extensions=["fenced_code", "tables"])
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


# ── Session helpers ───────────────────────────────────────────
def get_role(request: Request) -> str | None:
    """Returns 'admin', 'guest', or None."""
    return request.session.get("role")


def require_site_access(request: Request):
    """Any logged-in user (admin or guest) can access public pages."""
    if get_role(request) is None:
        raise HTTPException(303, headers={"Location": "/login"})


def require_admin(request: Request):
    """Only admins can access admin pages."""
    role = get_role(request)
    if role != "admin":
        target = "/login" if role is None else "/"
        raise HTTPException(303, headers={"Location": target})


# ── Login / logout ────────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_role(request) is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ip = request.client.host
    if _is_rate_limited(ip):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "too many failed attempts — try again in 15 minutes"},
            status_code=429,
        )
    valid = (
        username == ADMIN_USERNAME
        and ADMIN_PASSWORD_HASH
        and bcrypt.checkpw(password.encode(), ADMIN_PASSWORD_HASH)
    )
    if not valid:
        _record_failure(ip)
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "incorrect username or password"},
            status_code=401,
        )
    request.session["role"] = "admin"
    return RedirectResponse("/", status_code=303)


@app.post("/login/guest")
def login_guest(request: Request):
    request.session["role"] = "guest"
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ── Public routes (require any login) ────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    require_site_access(request)
    return templates.TemplateResponse(
        request, "index.html", {
            "projects": PROJECTS[:3],
            "role": get_role(request),
        }
    )


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request):
    require_site_access(request)
    return templates.TemplateResponse(
        request, "projects.html", {
            "projects": PROJECTS,
            "role": get_role(request),
            "breadcrumbs": [{"label": "projects", "url": None}],
        }
    )


@app.get("/blog", response_class=HTMLResponse)
def blog(request: Request):
    require_site_access(request)
    return templates.TemplateResponse(
        request, "blog.html", {
            "posts": load_posts(),
            "role": get_role(request),
            "breadcrumbs": [{"label": "blog", "url": None}],
        }
    )


@app.get("/blog/{slug}", response_class=HTMLResponse)
def post(request: Request, slug: str):
    require_site_access(request)
    for p in load_posts():
        if p["slug"] == slug:
            return templates.TemplateResponse(
                request, "post.html", {
                    "post": p,
                    "body_html": render_markdown(p["body"]),
                    "role": get_role(request),
                    "breadcrumbs": [
                        {"label": "blog", "url": "/blog"},
                        {"label": p["title"], "url": None},
                    ],
                },
            )
    raise HTTPException(status_code=404, detail="Post not found")


# ── Admin routes ──────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"posts": load_all_posts()}
    )


@app.get("/admin/new", response_class=HTMLResponse)
def admin_new(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        request, "admin/editor.html", {
            "post": None,
            "today": date.today().isoformat(),
        }
    )


@app.post("/admin/new")
def admin_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    date_: str = Form(..., alias="date"),
    draft: bool = Form(False),
    body: str = Form(""),
):
    require_admin(request)
    slug = slugify(title)
    path = BLOG_DIR / f"{slug}.md"
    if path.exists():
        slug = f"{slug}-2"
        path = BLOG_DIR / f"{slug}.md"
    p = frontmatter.Post(body, title=title, description=description,
                         date=date_, draft=draft)
    path.write_text(frontmatter.dumps(p))
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/edit/{slug}", response_class=HTMLResponse)
def admin_edit(request: Request, slug: str):
    require_admin(request)
    path = BLOG_DIR / f"{slug}.md"
    if not path.exists():
        raise HTTPException(status_code=404)
    p = frontmatter.load(path)
    return templates.TemplateResponse(
        request, "admin/editor.html", {
            "post": {
                "slug": slug,
                "title": p["title"],
                "description": p.get("description", ""),
                "date": p["date"],
                "draft": p.get("draft", False),
                "body": p.content,
            },
            "today": date.today().isoformat(),
        }
    )


@app.post("/admin/edit/{slug}")
def admin_update(
    request: Request,
    slug: str,
    title: str = Form(...),
    description: str = Form(""),
    date_: str = Form(..., alias="date"),
    draft: bool = Form(False),
    body: str = Form(""),
):
    require_admin(request)
    path = BLOG_DIR / f"{slug}.md"
    if not path.exists():
        raise HTTPException(status_code=404)
    p = frontmatter.Post(body, title=title, description=description,
                         date=date_, draft=draft)
    path.write_text(frontmatter.dumps(p))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete/{slug}")
def admin_delete(request: Request, slug: str):
    require_admin(request)
    path = BLOG_DIR / f"{slug}.md"
    if path.exists():
        path.unlink()
    return RedirectResponse("/admin", status_code=303)
