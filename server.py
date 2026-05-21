#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bizno local proxy server for biz-tracker-biznoapi.

Fetches and parses bizno.net pages server-side so the browser can call
http://localhost:5000 without CORS restrictions.

Requirements:
    pip install flask flask-cors requests beautifulsoup4

Run:
    python server.py

Endpoints:
    GET /health               → {"ok": true}
    GET /search?query=<name>  → {"candidates": [{"name", "url"}, ...]}
    GET /detail?url=<url>     → {name, business_no, size, status, ...}
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["*"])

BASE_URL = "https://www.bizno.net/"
ARTICLE_RE = re.compile(r"/article/(\d{10})")
BUSINESS_NO_RE = re.compile(r"(\d{3}-\d{2}-\d{5})")
PHONE_RE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}|\d[\d\s().\-]{6,}\d")
WAIT_PATTERNS = ("현재 접속인원이 많아", "접속대기", "reservation in stand-by state")

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    "Connection": "keep-alive",
})


# ── helpers ──────────────────────────────────────────────────────────────────

def compact_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def hyphenate_bno(value: str) -> str:
    digits = re.sub(r"\D+", "", value)
    if len(digits) != 10:
        return value
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def is_wait_page(html: str) -> bool:
    return any(p in html for p in WAIT_PATTERNS)


def result_section_html(html: str) -> str:
    m = re.search(r"키워드로\s*[\d,]+\s*개의\s*결과", html)
    start = m.start() if m else 0
    end = len(html)
    for marker in ("실시간 조회기업", "실시간 검색어", "주요기능"):
        at = html.find(marker, start)
        if at != -1:
            end = min(end, at)
    return html[start:end]


def parse_search_results(html: str) -> list[dict]:
    section = result_section_html(html)
    soup = BeautifulSoup(section, "html.parser")
    candidates: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=ARTICLE_RE):
        href = a.get("href") or ""
        url = href if href.startswith("http") else BASE_URL.rstrip("/") + href
        if url in seen:
            continue
        name = compact_text(a.get_text(" ", strip=True))
        if not name:
            continue
        seen.add(url)
        candidates.append({"name": name, "url": url})
    return candidates


def text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    return [compact_text(line) for line in text.splitlines() if compact_text(line)]


def field_after_label(
    lines: list[str],
    label: str,
    *,
    rejected: set[str] | None = None,
    pattern: re.Pattern | None = None,
) -> str:
    rej = rejected or set()
    for i, line in enumerate(lines):
        value = ""
        if line == label and i + 1 < len(lines):
            value = lines[i + 1]
        elif line.startswith(label):
            value = line[len(label):].strip(" : ")
        if not value:
            continue
        value = compact_text(value)
        if value in rej:
            continue
        if pattern and not pattern.search(value):
            continue
        return value
    return ""


def industry_category_text(lines: list[str]) -> str:
    labels = ("대분류", "중분류", "소분류", "세분류", "세세분류")
    vals: list[str] = []
    for line in lines:
        for label in labels:
            if line.startswith(label):
                vals.append(line.split(":", 1)[-1].strip() if ":" in line else line)
                break
    return " ".join(vals)


def parse_detail_page(html: str, fallback_url: str, fallback_name: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    lines = text_lines(html)

    name = fallback_name
    title = compact_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    if title and "사업자등록번호조회" not in title:
        name = title
    elif lines and lines[0] not in {"Home", "사업자등록번호조회"}:
        name = lines[0]

    all_text = "\n".join(lines)
    m = BUSINESS_NO_RE.search(all_text)
    bno = m.group(1) if m else ""
    if not bno:
        bno = field_after_label(
            lines, "사업자등록번호",
            rejected={"조회", "조회하기"},
            pattern=BUSINESS_NO_RE,
        )
    if not bno:
        am = ARTICLE_RE.search(fallback_url)
        if am:
            bno = hyphenate_bno(am.group(1))

    return {
        "name": name,
        "business_no": bno,
        "size": field_after_label(lines, "기업규모"),
        "entity_kind": field_after_label(lines, "법인구분"),
        "legal_type": field_after_label(lines, "법인형태"),
        "status": field_after_label(lines, "사업자 현재 상태"),
        "tax_type": field_after_label(lines, "과세유형"),
        "representative": field_after_label(lines, "대표자명"),
        "phone": field_after_label(
            lines, "전화번호",
            rejected={"로 조회", "조회"},
            pattern=PHONE_RE,
        ),
        "business_type": field_after_label(lines, "업 태"),
        "industry": field_after_label(lines, "종 목"),
        "industry_category": industry_category_text(lines),
        "address": field_after_label(lines, "회사주소"),
    }


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/search")
def search():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "query parameter required"}), 400
    try:
        resp = _session.get(BASE_URL, params={"query": query}, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        if is_wait_page(resp.text):
            return jsonify({"error": "bizno.net 접속 대기 중입니다. 잠시 후 재시도하세요."}), 503
        return jsonify({"candidates": parse_search_results(resp.text)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/detail")
def detail():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url parameter required"}), 400
    if not (url.startswith(BASE_URL) or url.startswith("https://bizno.net/")):
        return jsonify({"error": "URL must be a bizno.net page"}), 400
    try:
        resp = _session.get(url, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return jsonify(parse_detail_page(resp.text, url, ""))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Bizno 로컬 프록시 서버")
    print("  http://localhost:5000 에서 실행 중")
    print("  종료하려면 Ctrl+C 를 누르세요")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)
