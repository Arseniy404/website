import os
import re
from datetime import date, datetime
from pathlib import Path

import bcrypt
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


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=["fenced_code", "tables"])


def slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def check_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(
            status_code=303,
            headers={"Location": "/admin/login"},
        )


# ── Public routes ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"projects": PROJECTS[:3]}
    )


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request):
    return templates.TemplateResponse(
        request, "projects.html", {
            "projects": PROJECTS,
            "breadcrumbs": [{"label": "projects", "url": None}],
        }
    )


@app.get("/blog", response_class=HTMLResponse)
def blog(request: Request):
    return templates.TemplateResponse(
        request, "blog.html", {
            "posts": load_posts(),
            "breadcrumbs": [{"label": "blog", "url": None}],
        }
    )


@app.get("/blog/{slug}", response_class=HTMLResponse)
def post(request: Request, slug: str):
    for p in load_posts():
        if p["slug"] == slug:
            return templates.TemplateResponse(
                request, "post.html", {
                    "post": p,
                    "body_html": render_markdown(p["body"]),
                    "breadcrumbs": [
                        {"label": "blog", "url": "/blog"},
                        {"label": p["title"], "url": None},
                    ],
                },
            )
    raise HTTPException(status_code=404, detail="Post not found")


# ── Auth routes ───────────────────────────────────────────────
@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@app.post("/admin/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    valid = (
        username == ADMIN_USERNAME
        and ADMIN_PASSWORD_HASH
        and bcrypt.checkpw(password.encode(), ADMIN_PASSWORD_HASH)
    )
    if not valid:
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"error": "incorrect username or password"},
            status_code=401,
        )
    request.session["authenticated"] = True
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ── Admin routes ──────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    check_auth(request)
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"posts": load_all_posts()}
    )


@app.get("/admin/new", response_class=HTMLResponse)
def admin_new(request: Request):
    check_auth(request)
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
    check_auth(request)
    slug = slugify(title)
    path = BLOG_DIR / f"{slug}.md"
    if path.exists():
        slug = f"{slug}-2"
        path = BLOG_DIR / f"{slug}.md"

    post = frontmatter.Post(body, title=title, description=description,
                            date=date_, draft=draft)
    path.write_text(frontmatter.dumps(post))
    return RedirectResponse(f"/admin", status_code=303)


@app.get("/admin/edit/{slug}", response_class=HTMLResponse)
def admin_edit(request: Request, slug: str):
    check_auth(request)
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
    check_auth(request)
    path = BLOG_DIR / f"{slug}.md"
    if not path.exists():
        raise HTTPException(status_code=404)
    post = frontmatter.Post(body, title=title, description=description,
                            date=date_, draft=draft)
    path.write_text(frontmatter.dumps(post))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete/{slug}")
def admin_delete(request: Request, slug: str):
    check_auth(request)
    path = BLOG_DIR / f"{slug}.md"
    if path.exists():
        path.unlink()
    return RedirectResponse("/admin", status_code=303)
