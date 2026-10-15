"""Skill normalisation, partial matching and dictionary-based extraction."""

from __future__ import annotations

import re

ALIASES: dict[str, str] = {
    "js": "javascript",
    "es6": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "react js": "react",
    "nextjs": "next.js",
    "next": "next.js",
    "next js": "next.js",
    "vuejs": "vue",
    "vue.js": "vue",
    "nuxtjs": "nuxt",
    "nuxt.js": "nuxt",
    "angularjs": "angular",
    "svelte.js": "svelte",
    "node": "node.js",
    "nodejs": "node.js",
    "node js": "node.js",
    "expressjs": "express",
    "express.js": "express",
    "py": "python",
    "python3": "python",
    "postgres": "postgresql",
    "psql": "postgresql",
    "pg": "postgresql",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "aws lambda": "aws",
    "amazon web services": "aws",
    "gcp": "google cloud",
    "google cloud platform": "google cloud",
    "ml": "machine learning",
    "dl": "deep learning",
    "llm": "llms",
    "large language models": "llms",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "openai api": "openai",
    "chatgpt api": "openai",
    "tailwindcss": "tailwind css",
    "tailwind": "tailwind css",
    "rest": "rest api",
    "restful": "rest api",
    "restful api": "rest api",
    "rest apis": "rest api",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "golang": "go",
    "c sharp": "c#",
    "csharp": "c#",
    ".net": ".net",
    "dotnet": ".net",
    "ui/ux": "ui/ux design",
    "ux": "ui/ux design",
    "ui design": "ui/ux design",
    "wp": "wordpress",
    "shopify development": "shopify",
    "seo optimization": "seo",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "huggingface": "hugging face",
    "rn": "react native",
    "react-native": "react native",
}

# Skills in the same family count as a partial match for each other.
FAMILIES: list[set[str]] = [
    {"react", "next.js", "react native", "redux", "gatsby"},
    {"vue", "nuxt"},
    {"javascript", "typescript"},
    {"node.js", "express", "nestjs"},
    {"python", "django", "fastapi", "flask"},
    {"postgresql", "mysql", "sqlite", "sql", "sql server"},
    {"mongodb", "dynamodb", "firebase"},
    {"aws", "google cloud", "azure"},
    {"docker", "kubernetes"},
    {"machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn"},
    {"llms", "openai", "generative ai", "langchain", "rag", "prompt engineering", "hugging face"},
    {"css", "tailwind css", "sass", "bootstrap"},
    {"figma", "ui/ux design", "adobe xd"},
    {"wordpress", "php", "laravel", "woocommerce"},
    {"shopify", "woocommerce", "ecommerce"},
    {"ios", "swift"},
    {"android", "kotlin"},
    {"flutter", "dart"},
    {"data analysis", "pandas", "excel", "power bi", "tableau"},
    {"web scraping", "selenium", "playwright", "beautifulsoup"},
    {"chrome extension", "javascript"},
    {"seo", "content writing", "copywriting"},
]

KNOWN_SKILLS: set[str] = (
    set().union(*FAMILIES)
    | set(ALIASES.values())
    | {
        "html",
        "graphql",
        "rest api",
        "git",
        "ci/cd",
        "go",
        "rust",
        "java",
        "c#",
        ".net",
        "c++",
        "ruby",
        "rails",
        "terraform",
        "linux",
        "redis",
        "elasticsearch",
        "stripe",
        "twilio",
        "zapier",
        "n8n",
        "airtable",
        "supabase",
        "vector databases",
        "chromadb",
        "pinecone",
        "faiss",
        "nlp",
        "computer vision",
        "opencv",
        "data engineering",
        "etl",
        "spark",
        "airflow",
        "snowflake",
        "bigquery",
        "jest",
        "cypress",
        "testing",
        "qa",
        "devops",
        "project management",
        "technical writing",
        "api integration",
        "microservices",
        "websockets",
        "three.js",
        "unity",
        "blender",
        "video editing",
        "graphic design",
        "illustrator",
        "photoshop",
        "marketing",
    }
)


def normalize_skill(skill: str) -> str:
    s = re.sub(r"\s+", " ", skill.strip().lower())
    return ALIASES.get(s, s)


def normalize_skills(skills: list[str]) -> list[str]:
    out: list[str] = []
    for s in skills:
        n = normalize_skill(s)
        if n and n not in out:
            out.append(n)
    return out


def related(a: str, b: str) -> bool:
    return any(a in fam and b in fam for fam in FAMILIES)


def extract_skills_from_text(text: str, limit: int = 40) -> list[str]:
    """Find known skills mentioned in free text (word-boundary match, aliases included)."""
    lowered = f" {text.lower()} "
    found: list[str] = []
    candidates = sorted(KNOWN_SKILLS | set(ALIASES.keys()), key=len, reverse=True)
    for cand in candidates:
        if len(cand) <= 2 and cand not in {"go", "c#", "qa", "ml", "js", "ts"}:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(cand) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            norm = normalize_skill(cand)
            if norm == "go" and not re.search(r"(?<![a-z])(golang|go developer|go language|in go)(?![a-z])", lowered):
                continue
            if norm not in found:
                found.append(norm)
        if len(found) >= limit:
            break
    return found


def match_skills(required: list[str], primary: list[str], additional: list[str]) -> dict[str, list]:
    """Classify required skills as matched / partial / missing against the profile."""
    req = normalize_skills(required)
    prim = normalize_skills(primary)
    addl = normalize_skills(additional)
    have = prim + [s for s in addl if s not in prim]
    matched: list[str] = []
    partial: list[dict[str, str]] = []
    missing: list[str] = []
    for r in req:
        if r in have:
            matched.append(r)
            continue
        rel = next((h for h in have if related(r, h)), None)
        if rel is None:
            # Substring heuristics, e.g. "react hooks" vs "react".
            rel = next((h for h in have if len(h) > 2 and (h in r.split() or r in h.split())), None)
        if rel is not None:
            partial.append({"skill": r, "via": rel})
        else:
            missing.append(r)
    return {"matched": matched, "partial": partial, "missing": missing}
