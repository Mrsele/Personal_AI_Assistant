"""Web search integration using DuckDuckGo."""
import html
import logging
import re
import urllib.parse
import httpx

logger = logging.getLogger(__name__)


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the public web and return titles, URLs, and snippets."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=headers,
                timeout=10.0,
            )
            html_text = resp.text
    except Exception as e:
        logger.error(f"Web search request failed for query '{query}': {e}")
        return []

    # Extract snippets and titles
    raw_snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL)
    raw_titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL)

    results = []
    for i in range(min(len(raw_titles), max_results)):
        raw_url, raw_title = raw_titles[i]
        snippet_raw = raw_snippets[i] if i < len(raw_snippets) else ""
        
        # Clean HTML tags and unescape entities
        title = html.unescape(re.sub(r"<[^<]+?>", "", raw_title)).strip()
        snippet = html.unescape(re.sub(r"<[^<]+?>", "", snippet_raw)).strip()
        
        # Extract target URL from DDG redirect url (/uddg=...)
        actual_url = raw_url
        if "uddg=" in raw_url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
            if "uddg" in parsed:
                actual_url = parsed["uddg"][0]

        results.append({
            "title": title,
            "url": actual_url,
            "snippet": snippet,
        })

    return results
