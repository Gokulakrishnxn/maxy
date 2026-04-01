from duckduckgo_search import DDGS

def web_search(query: str, max_results: int = 4) -> str:
    """Search the web using DuckDuckGo — no API key needed."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body  = r.get("body",  "")[:200]
            href  = r.get("href",  "")
            lines.append(f"{i}. {title}\n   {body}\n   {href}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"
