from pathlib import Path

import frontmatter
import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
BLOG_DIR = BASE_DIR / "content" / "blog"

app = FastAPI(title="arseniy")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Add your projects here.
PROJECTS = [
    {
        "title": "my website",
        "description": "This site. Built with FastAPI, Jinja2 and a little vanilla CSS.",
        "tags": ["fastapi", "jinja2", "python"],
        "github": "https://github.com/Arseniy404/website",
        "demo": "/",
    },
]


def load_posts() -> list[dict]:
    """Read every markdown file in content/blog, newest first."""
    posts = []
    for path in BLOG_DIR.glob("*.md"):
        post = frontmatter.load(path)
        if post.get("draft", False):
            continue
        posts.append(
            {
                "slug": path.stem,
                "title": post["title"],
                "description": post.get("description", ""),
                "date": post["date"],
                "body": post.content,
            }
        )
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=["fenced_code", "tables"])


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"projects": PROJECTS[:3]}
    )


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request):
    return templates.TemplateResponse(
        request, "projects.html", {"projects": PROJECTS}
    )


@app.get("/blog", response_class=HTMLResponse)
def blog(request: Request):
    return templates.TemplateResponse(request, "blog.html", {"posts": load_posts()})


@app.get("/blog/{slug}", response_class=HTMLResponse)
def post(request: Request, slug: str):
    for p in load_posts():
        if p["slug"] == slug:
            return templates.TemplateResponse(
                request,
                "post.html",
                {"post": p, "body_html": render_markdown(p["body"])},
            )
    raise HTTPException(status_code=404, detail="Post not found")
