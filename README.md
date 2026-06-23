# website

Personal site — projects, blog, experiments. Built with FastAPI + Jinja2.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://localhost:8000

## Structure

- `main.py` — FastAPI app and routes
- `templates/` — Jinja2 HTML templates
- `static/style.css` — styles
- `content/blog/*.md` — blog posts (markdown with frontmatter)

## Add a blog post

Create a markdown file in `content/blog/`:

```markdown
---
title: "My post"
description: "Short summary"
date: 2026-06-23
---

Post body in **markdown**.
```

## Add a project

Edit the `PROJECTS` list in `main.py`.
