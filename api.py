import re
import json
import httpx
import asyncio
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI(
    title="MovieBox API Pro",
    description="Full Pure REST API for moviebox.ph — Zero Scraping",
    version="2.1.5"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://moviebox.ph"
API_BASE = "https://h5-api.aoneroom.com/wefeed-h5api-bff"

_bearer_token: str | None = None

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Referer": "https://moviebox.ph/",
    "Origin": "https://moviebox.ph",
    "X-Client-Info": '{"timezone":"Asia/Dhaka"}',
    "X-Request-Lang": "en",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}

# Player-side headers for the stream domain (netfilm.world)
PLAYER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "X-Client-Info": '{"timezone":"Asia/Dhaka"}',
    "X-Source": "",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

async def _get_bearer_token() -> str:
    """Auto-acquire a guest JWT from the x-user response header."""
    global _bearer_token
    if _bearer_token:
        return _bearer_token
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        resp = await client.get(f"{API_BASE}/home?host=moviebox.ph", headers=DEFAULT_HEADERS)
        x_user = resp.headers.get("x-user")
        if x_user:
            _bearer_token = json.loads(x_user).get("token")
        if not _bearer_token:
            # fallback: read from set-cookie
            cookie = resp.headers.get("set-cookie", "")
            import re as _re
            m = _re.search(r"token=([^;]+)", cookie)
            if m:
                _bearer_token = m.group(1)
    return _bearer_token or ""

async def _make_request(url: str, method: str = "GET", payload: dict = None, custom_headers: dict = None) -> dict:
    global _bearer_token
    token = await _get_bearer_token()
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {token}" if token else "",
        **(custom_headers or {})
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        try:
            if method == "POST":
                resp = await client.post(url, headers=headers, json=payload)
            else:
                resp = await client.get(url, headers=headers)

            # Refresh token if server sends a new one
            x_user = resp.headers.get("x-user")
            if x_user:
                new_token = json.loads(x_user).get("token")
                if new_token:
                    _bearer_token = new_token

            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Upstream API error: {resp.status_code}")

            return resp.json()
        except Exception as e:
            if isinstance(e, HTTPException): raise e
            raise HTTPException(status_code=502, detail=f"Request failed: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MovieBox Pure API | Pro Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <script src="https://cdn.jsdelivr.net/npm/dashjs@latest/dist/dash.all.min.js"></script>
        <style>
            :root {
                --primary: #ff3d71;
                --secondary: #3366ff;
                --accent: #00f2ff;
                --bg: #07080c;
                --card-bg: rgba(255, 255, 255, 0.03);
                --glass: rgba(255, 255, 255, 0.06);
                --text: #ffffff;
            }

            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: 'Outfit', sans-serif;
                background: var(--bg);
                color: var(--text);
                overflow-x: hidden;
                min-height: 100vh;
                background-image: 
                    radial-gradient(circle at 10% 10%, rgba(255, 61, 113, 0.12) 0%, transparent 40%),
                    radial-gradient(circle at 90% 90%, rgba(51, 102, 255, 0.12) 0%, transparent 40%);
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 60px 24px;
                position: relative;
            }

            header {
                text-align: center;
                margin-bottom: 80px;
                animation: fadeInDown 1s ease-out;
            }

            @keyframes fadeInDown {
                from { opacity: 0; transform: translateY(-30px); }
                to { opacity: 1; transform: translateY(0); }
            }

            h1 {
                font-size: clamp(2.5rem, 8vw, 4rem);
                font-weight: 800;
                background: linear-gradient(135deg, #fff 0%, #aaa 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 15px;
                letter-spacing: -2px;
            }

            .badge {
                background: linear-gradient(90deg, var(--primary), var(--secondary));
                padding: 8px 18px;
                border-radius: 40px;
                font-size: 0.85rem;
                font-weight: 700;
                display: inline-block;
                margin-bottom: 25px;
                text-transform: uppercase;
                letter-spacing: 1px;
                box-shadow: 0 10px 30px rgba(255, 61, 113, 0.3);
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
                gap: 30px;
                margin-top: 20px;
            }

            .card {
                background: var(--card-bg);
                border: 1px solid var(--glass);
                border-radius: 28px;
                padding: 35px;
                transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                backdrop-filter: blur(12px);
                position: relative;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            @media (hover: hover) {
                .card:hover {
                    transform: translateY(-12px) scale(1.02);
                    border-color: rgba(255,255,255,0.2);
                    box-shadow: 0 30px 60px rgba(0,0,0,0.5);
                }
            }

            .card-title {
                font-size: 1.5rem;
                font-weight: 700;
                margin-bottom: 18px;
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .card-title i {
                width: 32px; height: 32px;
                background: rgba(255,255,255,0.05);
                border-radius: 8px;
                display: flex; align-items: center; justify-content: center;
                font-size: 1rem; color: var(--accent);
                font-style: normal;
            }

            .card-desc {
                color: #9ea3ac;
                font-size: 1rem;
                line-height: 1.6;
                margin-bottom: 25px;
                flex-grow: 1;
            }

            .endpoint {
                font-family: 'JetBrains Mono', monospace;
                background: rgba(0,0,0,0.4);
                padding: 14px;
                border-radius: 14px;
                font-size: 0.85rem;
                color: var(--accent);
                border: 1px solid rgba(0,242,255,0.15);
                margin-bottom: 25px;
                word-break: break-all;
                position: relative;
            }

            .endpoint::after {
                content: 'GET';
                position: absolute;
                right: 14px; top: 14px;
                font-size: 0.65rem; font-weight: 800;
                color: rgba(255,255,255,0.3);
            }

            .btn {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 16px;
                background: #ffffff;
                color: #000000;
                text-decoration: none;
                border-radius: 16px;
                font-weight: 700;
                font-size: 0.95rem;
                transition: all 0.3s;
                border: none;
                cursor: pointer;
            }

            .btn:hover {
                background: var(--primary);
                color: #fff;
                transform: translateY(-2px);
                box-shadow: 0 10px 25px rgba(255, 61, 113, 0.4);
            }

            /* Playground Styles */
            .playground-header {
                margin: 80px 0 30px;
                text-align: center;
                border-top: 1px solid rgba(255,255,255,0.1);
                padding-top: 50px;
            }

            .playground-header h2 {
                font-size: 2.2rem;
                font-weight: 800;
                background: linear-gradient(90deg, var(--accent), var(--secondary));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }

            .playground-header p {
                color: #888;
                font-size: 1rem;
            }

            .search-section {
                margin-bottom: 40px;
            }

            .search-bar {
                display: flex;
                gap: 15px;
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid var(--glass);
                padding: 10px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }

            .search-input {
                flex-grow: 1;
                background: transparent;
                border: none;
                color: #fff;
                font-family: inherit;
                font-size: 1.1rem;
                outline: none;
                padding: 0 15px;
            }

            .btn-accent {
                background: var(--primary);
                color: #fff;
            }

            .btn-accent:hover {
                background: var(--secondary);
                box-shadow: 0 10px 25px rgba(51, 102, 255, 0.4);
            }

            .main-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 30px;
                margin-bottom: 60px;
            }

            @media (min-width: 900px) {
                .main-grid {
                    grid-template-columns: 350px 1fr;
                }
            }

            .panel {
                background: var(--card-bg);
                border: 1px solid var(--glass);
                border-radius: 24px;
                padding: 25px;
                backdrop-filter: blur(12px);
                max-height: 80vh;
                overflow-y: auto;
            }

            .panel-title {
                font-size: 1.25rem;
                font-weight: 700;
                margin-bottom: 20px;
                color: #fff;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                padding-bottom: 10px;
            }

            .search-results {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .result-item {
                display: flex;
                gap: 12px;
                background: rgba(255,255,255,0.02);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 14px;
                padding: 10px;
                cursor: pointer;
                transition: all 0.2s;
            }

            .result-item:hover, .result-item.active {
                background: rgba(255,255,255,0.08);
                border-color: var(--accent);
            }

            .result-poster {
                width: 50px;
                height: 75px;
                object-fit: cover;
                border-radius: 8px;
                background: #111;
            }

            .result-info {
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: 4px;
            }

            .result-name {
                font-size: 0.95rem;
                font-weight: 600;
                color: #fff;
                line-height: 1.2;
            }

            .result-meta {
                font-size: 0.75rem;
                color: #888;
            }

            .detail-card {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }

            .detail-header {
                display: flex;
                gap: 20px;
            }

            .detail-poster {
                width: 100px;
                height: 150px;
                object-fit: cover;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.1);
            }

            .detail-header-info {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .detail-title {
                font-size: 1.5rem;
                font-weight: 800;
            }

            .tag {
                background: rgba(255,255,255,0.05);
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
                display: inline-block;
                margin-right: 5px;
            }

            .rating {
                color: #ffc107;
                font-weight: 700;
            }

            .selectors {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 10px;
            }

            .select-group {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .select-group label {
                font-size: 0.85rem;
                font-weight: 600;
                color: #888;
                text-transform: uppercase;
                letter-spacing: 1px;
            }

            select {
                background: rgba(0,0,0,0.5);
                border: 1px solid rgba(255,255,255,0.1);
                color: #fff;
                padding: 12px;
                border-radius: 10px;
                font-family: inherit;
                font-size: 1rem;
                outline: none;
                cursor: pointer;
            }

            select:focus {
                border-color: var(--accent);
            }

            .source-list {
                margin-top: 25px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .source-card {
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 16px;
                padding: 15px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 15px;
            }

            .source-meta {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .source-badge {
                background: var(--accent);
                color: #000;
                font-size: 0.75rem;
                font-weight: 800;
                padding: 3px 8px;
                border-radius: 6px;
                text-transform: uppercase;
                width: max-content;
            }

            .source-title {
                font-size: 1.1rem;
                font-weight: 700;
            }

            .source-details {
                font-size: 0.8rem;
                color: #888;
                font-family: 'JetBrains Mono', monospace;
            }

            .source-actions {
                display: flex;
                gap: 8px;
            }

            .btn-sm {
                padding: 8px 14px;
                font-size: 0.85rem;
                border-radius: 8px;
            }

            .player-container {
                margin-top: 25px;
                background: #000;
                border-radius: 20px;
                overflow: hidden;
                border: 1px solid var(--glass);
                aspect-ratio: 16/9;
                position: relative;
            }

            video {
                width: 100%;
                height: 100%;
                display: block;
            }

            .empty-player-placeholder {
                position: absolute;
                inset: 0;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                color: #555;
                font-weight: 600;
                gap: 10px;
                background: rgba(0,0,0,0.9);
            }

            .empty-player-placeholder svg {
                width: 50px;
                height: 50px;
                fill: currentColor;
                margin-bottom: 10px;
            }

            footer {
                text-align: center;
                padding: 80px 0 40px;
                animation: fadeIn 2s ease;
            }

            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

            .dev-tag {
                font-weight: 800;
                color: #666;
                letter-spacing: 3px;
                text-transform: uppercase;
                font-size: 0.75rem;
                border: 1px solid #222;
                padding: 12px 30px;
                border-radius: 50px;
                display: inline-block;
                background: rgba(255,255,255,0.01);
                transition: all 0.3s;
            }

            .dev-tag:hover {
                color: var(--text);
                border-color: var(--primary);
                letter-spacing: 5px;
            }

            @media (max-width: 480px) {
                .container { padding: 40px 16px; }
                .card { padding: 25px; }
                h1 { margin-bottom: 10px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="badge">Enterprise API Solution</div>
                <h1>MovieBox Pro</h1>
                <p style="color: #667; font-size: 1.25rem; font-weight: 300;">State-of-the-Art Pure API Architecture</p>
            </header>

            <div class="grid">
                <div class="card">
                    <div class="card-title"><i>🏠</i> Discover Home</div>
                    <p class="card-desc">The ultimate window into MovieBox. Headlines, recommended content, and trending blocks updated in real-time.</p>
                    <div class="endpoint">/home</div>
                    <a href="/home" target="_blank" class="btn">Launch API</a>
                </div>

                <div class="card">
                    <div class="card-title"><i>🔍</i> Smart Search</div>
                    <p class="card-desc">High-precision search engine results. Returns titles, posters, and slugs for lightning-fast matching.</p>
                    <div class="endpoint">/search?q=Attack on Titan</div>
                    <a href="/search?q=Attack on Titan" target="_blank" class="btn">Test Search</a>
                </div>

                <div class="card">
                    <div class="card-title"><i>🆔</i> Metadata A-Z</div>
                    <p class="card-desc">Deep-dive into any subject. Episodes, seasons, languages, and full high-resolution metadata trees.</p>
                    <div class="endpoint">/detail/{slug}</div>
                    <a href="/detail/attack-on-titan-hindi-kGWQOIx0d4" target="_blank" class="btn">Fetch Specs</a>
                </div>

                <div class="card">
                    <div class="card-title"><i>🎬</i> Stream Engine</div>
                    <p class="card-desc">Dynamic domain discovery and direct MP4 extraction. Supports multiple resolutions and qualities.</p>
                    <div class="endpoint">/api/stream/{subject_id}</div>
                    <a href="/api/stream/56988683026712168?detail_path=attack-on-titan-hindi-kGWQOIx0d4" target="_blank" class="btn">Get Player Link</a>
                </div>

                <div class="card">
                    <div class="card-title"><i>📦</i> Catalog Filters</div>
                    <p class="card-desc">Paginated collections for all genres. Movies, TV shows, and Animations filtered by professional criteria. Pagination Supported.</p>
                    <div class="endpoint">/tv-series?page=2</div>
                    <a href="/tv-series?page=2" target="_blank" class="btn">Test Page 2</a>
                </div>

                <div class="card">
                    <div class="card-title"><i>💬</i> Subtitle Suite</div>
                    <p class="card-desc">Access to the complete SRT/VTT global database for all streaming subjects.</p>
                    <div class="endpoint">/api/stream/{id}/captions</div>
                    <a href="/api/stream/6207982430134357800/captions?detail_path=breaking-bad-ej6Bp0MCAo7" target="_blank" class="btn">Retrive Subs</a>
                </div>
            </div>

            <!-- Developer Playground Title -->
            <div class="playground-header">
                <h2>Developer Playground & Player Testing</h2>
                <p>Verify stream generation and test direct video playback (MP4, HLS, DASH) in real-time.</p>
            </div>

            <!-- Search Area -->
            <div class="search-section">
                <div class="search-bar">
                    <input type="text" id="searchInput" class="search-input" placeholder="Search movies, TV series, or enter title..." value="Love Island USA">
                    <button class="btn btn-accent" id="searchBtn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px; display: inline-block; vertical-align: middle;"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        Search
                    </button>
                </div>
            </div>

            <!-- Main Layout Grid -->
            <div class="main-grid">
                <!-- Search results -->
                <div class="panel">
                    <div class="panel-title">Search Results</div>
                    <div class="search-results" id="searchResults">
                        <div style="color: #666; text-align: center; padding: 20px;">Search for a title to begin</div>
                    </div>
                </div>

                <!-- Controller / Player -->
                <div class="panel">
                    <div class="panel-title" id="controllerTitle">Stream Controller</div>
                    
                    <div id="mediaDetails" style="display: none;">
                        <div class="detail-card">
                            <div class="detail-header">
                                <img src="" id="detailPoster" class="detail-poster">
                                <div class="detail-header-info">
                                    <div class="detail-title" id="detailTitle">Title</div>
                                    <div>
                                        <span class="tag rating" id="detailRating">★ -</span>
                                        <span class="tag" id="detailYear">-</span>
                                        <span class="tag" id="detailType">-</span>
                                    </div>
                                    <p id="detailDesc" style="font-size: 0.9rem; color: #888; margin-top: 10px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;"></p>
                                </div>
                            </div>

                            <div class="selectors" id="seSelectorContainer" style="display: none;">
                                <div class="select-group">
                                    <label>Season</label>
                                    <select id="seSelect"></select>
                                </div>
                                <div class="select-group">
                                    <label>Episode</label>
                                    <select id="epSelect"></select>
                                </div>
                            </div>

                            <button class="btn btn-accent" id="retrieveBtn" style="margin-top: 10px; width: 100%;">Retrieve Stream Sources</button>
                        </div>

                        <!-- Resolved Sources List -->
                        <div id="sourcesSection" style="display: none; border-top: 1px solid rgba(255,255,255,0.05); margin-top: 25px; padding-top: 25px;">
                            <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 15px;">Resolved Stream URLs</h3>
                            <div class="source-list" id="sourceList"></div>
                        </div>

                        <!-- Video Player Area -->
                        <div class="player-container">
                            <div class="empty-player-placeholder" id="playerPlaceholder">
                                <svg viewBox="0 0 24 24" style="fill: #555; width: 48px; height: 48px;"><path d="M8 5v14l11-7z"/></svg>
                                <span>No stream loaded. Select a source to play.</span>
                            </div>
                            <video id="player" controls style="display: none;"></video>
                        </div>
                    </div>
                </div>
            </div>

            <footer>
                <div class="dev-tag">Developer: Walter</div>
            </footer>
        </div>

        <script>
            // State
            let selectedItem = null;
            let detailData = null;
            let dashPlayer = null;
            let hlsPlayer = null;

            // DOM elements
            const searchInput = document.getElementById('searchInput');
            const searchBtn = document.getElementById('searchBtn');
            const searchResults = document.getElementById('searchResults');
            const mediaDetails = document.getElementById('mediaDetails');
            const detailPoster = document.getElementById('detailPoster');
            const detailTitle = document.getElementById('detailTitle');
            const detailRating = document.getElementById('detailRating');
            const detailYear = document.getElementById('detailYear');
            const detailType = document.getElementById('detailType');
            const detailDesc = document.getElementById('detailDesc');
            const seSelectorContainer = document.getElementById('seSelectorContainer');
            const seSelect = document.getElementById('seSelect');
            const epSelect = document.getElementById('epSelect');
            const retrieveBtn = document.getElementById('retrieveBtn');
            const sourcesSection = document.getElementById('sourcesSection');
            const sourceList = document.getElementById('sourceList');
            const player = document.getElementById('player');
            const playerPlaceholder = document.getElementById('playerPlaceholder');

            // Search execution
            async function executeSearch() {
                const query = searchInput.value.trim();
                if (!query) return;

                searchResults.innerHTML = '<div style="color: #888; text-align: center; padding: 20px;">Searching...</div>';
                try {
                    const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
                    const data = await response.json();
                    
                    if (!data.items || data.items.length === 0) {
                        searchResults.innerHTML = '<div style="color: #888; text-align: center; padding: 20px;">No results found</div>';
                        return;
                    }

                    searchResults.innerHTML = '';
                    data.items.forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'result-item';
                        div.innerHTML = `
                            <img src="${item.poster_url || ''}" class="result-poster">
                            <div class="result-info">
                                <div class="result-name">${item.name}</div>
                                <div class="result-meta">ID: ${item.subject_id}</div>
                            </div>
                        `;
                        div.onclick = () => selectItem(item, div);
                        searchResults.appendChild(div);
                    });
                } catch (err) {
                    searchResults.innerHTML = `<div style="color: #ff3d71; text-align: center; padding: 20px;">Error: ${err.message}</div>`;
                }
            }

            // Select an item from results list
            async function selectItem(item, element) {
                // Clear active states
                document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
                element.classList.add('active');

                selectedItem = item;
                mediaDetails.style.display = 'block';
                sourcesSection.style.display = 'none';
                
                // Set temporary UI
                detailPoster.src = item.poster_url || '';
                detailTitle.textContent = item.name;
                detailRating.textContent = '★ -';
                detailYear.textContent = '-';
                detailType.textContent = '-';
                detailDesc.textContent = 'Fetching details...';
                seSelectorContainer.style.display = 'none';

                try {
                    const response = await fetch(`/detail/${item.slug}`);
                    const json = await response.json();
                    detailData = json.data;

                    const subject = detailData.subject || {};
                    detailRating.textContent = `★ ${subject.imdbRatingValue || 'N/A'}`;
                    detailYear.textContent = subject.releaseDate ? subject.releaseDate.substring(0, 4) : 'N/A';
                    detailType.textContent = subject.subjectType === 2 ? 'TV Show' : 'Movie';
                    detailDesc.textContent = subject.description || 'No description available.';

                    // Populate seasons dropdown if TV Show
                    const seasons = (detailData.subject && detailData.subject.season) || [];
                    if (subject.subjectType === 2 && seasons.length > 0) {
                        seSelectorContainer.style.display = 'grid';
                        seSelect.innerHTML = '';
                        
                        seasons.forEach(season => {
                            const option = document.createElement('option');
                            option.value = season.season;
                            option.textContent = `Season ${season.season}`;
                            seSelect.appendChild(option);
                        });

                        // Populate episodes based on selected season
                        seSelect.onchange = () => {
                            const selectedSe = seSelect.value;
                            const seasonConfig = seasons.find(s => s.season == selectedSe);
                            // Populate episodes (default to 50 options for TV series)
                            epSelect.innerHTML = '';
                            for (let i = 1; i <= 50; i++) {
                                const option = document.createElement('option');
                                option.value = i;
                                option.textContent = `Episode ${i}`;
                                epSelect.appendChild(option);
                            }
                        };
                        // Trigger initial change
                        seSelect.onchange();
                    } else {
                        seSelectorContainer.style.display = 'none';
                        window.movieSe = 1;
                        window.movieEp = 1;
                    }
                } catch (err) {
                    detailDesc.textContent = `Failed to fetch details: ${err.message}`;
                }
            }

            // Retrieve streaming sources
            async function getSources() {
                if (!selectedItem) return;

                const se = seSelectorContainer.style.display === 'none' ? (window.movieSe !== undefined ? window.movieSe : 1) : seSelect.value;
                const ep = seSelectorContainer.style.display === 'none' ? (window.movieEp !== undefined ? window.movieEp : 1) : epSelect.value;

                sourceList.innerHTML = '<div style="color: #888;">Discovering player domain & fetching stream URLs...</div>';
                sourcesSection.style.display = 'block';

                // Scroll to sources
                sourcesSection.scrollIntoView({ behavior: 'smooth' });

                // Initialize empty captions list
                window.currentCaptions = [];

                try {
                    // Fetch streams
                    const url = `/api/stream/${selectedItem.subject_id}?detail_path=${selectedItem.slug}&se=${se}&ep=${ep}`;
                    const response = await fetch(url);
                    const streamData = await response.json();

                    // Fetch captions concurrently
                    try {
                        const capUrl = `/api/stream/${selectedItem.subject_id}/captions?detail_path=${selectedItem.slug}&se=${se}&ep=${ep}`;
                        const capResponse = await fetch(capUrl);
                        const capData = await capResponse.json();
                        window.currentCaptions = capData.captions || [];
                    } catch (capErr) {
                        console.error("Failed to load captions", capErr);
                    }

                    sourceList.innerHTML = '';

                    const mp4Sources = streamData.sources || [];
                    const dashSources = streamData.dash || [];
                    const hlsSources = streamData.hls || [];

                    const allSources = [];
                    mp4Sources.forEach(s => allSources.push({ ...s, type: 'MP4' }));
                    dashSources.forEach(s => allSources.push({ ...s, type: 'DASH', resolution: `${s.resolutions || 'Auto'}p` }));
                    hlsSources.forEach(s => allSources.push({ ...s, type: 'HLS', resolution: `${s.resolutions || 'Auto'}p` }));

                    if (allSources.length === 0) {
                        sourceList.innerHTML = `<div style="color: var(--primary); font-weight: 600;">${streamData.note || 'No stream sources found for this subject/episode.'}</div>`;
                        return;
                    }

                    allSources.forEach(src => {
                        const playUrl = src.url;
                        if (!playUrl) return;

                        const card = document.createElement('div');
                        card.className = 'source-card';
                        
                        let badgeColor = 'var(--accent)';
                        if (src.type === 'HLS') badgeColor = '#ffc107';
                        if (src.type === 'MP4') badgeColor = '#4caf50';

                        card.innerHTML = `
                            <div class="source-meta">
                                <span class="source-badge" style="background: ${badgeColor}; color: ${src.type === 'MP4' ? '#fff' : '#000'}">${src.type}</span>
                                <div class="source-title">${src.resolution || 'Direct Link'}</div>
                                <div class="source-details">
                                    Codec: ${src.codec || src.codecName || 'h264'} ${src.size ? `&bull; Size: ${(src.size / (1024 * 1024)).toFixed(1)} MB` : ''}
                                </div>
                            </div>
                            <div class="source-actions">
                                <button class="btn btn-sm" onclick="copyToClipboard('${playUrl}')">Copy Link</button>
                                <button class="btn btn-sm btn-accent" onclick="startPlayback('${playUrl}', '${src.type}')">Test Stream</button>
                            </div>
                        `;
                        sourceList.appendChild(card);
                    });
                } catch (err) {
                    sourceList.innerHTML = `<div style="color: var(--primary);">Failed to get streams: ${err.message}</div>`;
                }
            }

            // Copy link utility
            function copyToClipboard(text) {
                navigator.clipboard.writeText(text).then(() => {
                    alert('Stream link copied to clipboard!');
                }).catch(err => {
                    alert('Could not copy link: ' + err);
                });
            }

            // Player stream control
            function startPlayback(url, format) {
                // Reset existing players
                if (dashPlayer) {
                    dashPlayer.destroy();
                    dashPlayer = null;
                }
                if (hlsPlayer) {
                    hlsPlayer.destroy();
                    hlsPlayer = null;
                }

                // Reset video element source and clear tracks
                player.src = "";
                while (player.firstChild) {
                    player.removeChild(player.firstChild);
                }

                player.style.display = 'block';
                playerPlaceholder.style.display = 'none';

                const proxyUrl = '/api/proxy?url=' + encodeURIComponent(url);
                const lowerUrl = url.toLowerCase();

                // Append subtitle tracks if available
                if (window.currentCaptions && window.currentCaptions.length > 0) {
                    const langMap = {
                        'en': 'English',
                        'es': 'Spanish',
                        'fr': 'French',
                        'de': 'German',
                        'it': 'Italian',
                        'pt': 'Portuguese',
                        'ru': 'Russian',
                        'zh': 'Chinese',
                        'ja': 'Japanese',
                        'ko': 'Korean',
                        'id': 'Indonesian',
                        'ms': 'Malay',
                        'th': 'Thai',
                        'vi': 'Vietnamese',
                        'ar': 'Arabic',
                        'hi': 'Hindi',
                        'tl': 'Tagalog'
                    };
                    window.currentCaptions.forEach((cap, index) => {
                        if (!cap.url) return;
                        const track = document.createElement('track');
                        track.kind = 'captions';
                        
                        const lanCode = (cap.lan || 'en').toLowerCase().split('_')[0];
                        const cleanLabel = langMap[lanCode] || cap.lanName || `Subtitle ${index + 1}`;

                        track.label = cleanLabel;
                        track.srclang = lanCode;
                        // Subtitles route through the converting proxy to convert SRT -> VTT
                        track.src = '/api/proxy?url=' + encodeURIComponent(cap.url);
                        if (cleanLabel.toLowerCase() === 'english') {
                            track.default = true;
                        }
                        player.appendChild(track);
                    });
                }
                
                if (format === 'DASH' || lowerUrl.includes('.mpd')) {
                    // Load Dash Player
                    dashPlayer = dashjs.MediaPlayer().create();
                    dashPlayer.initialize(player, proxyUrl, true);
                } else if (format === 'HLS' || lowerUrl.includes('.m3u8')) {
                    // Load HLS.js
                    if (Hls.isSupported()) {
                        hlsPlayer = new Hls();
                        hlsPlayer.loadSource(proxyUrl);
                        hlsPlayer.attachMedia(player);
                        hlsPlayer.on(Hls.Events.MANIFEST_PARSED, function() {
                            player.play();
                        });
                    } else if (player.canPlayType('application/vnd.apple.mpegurl')) {
                        player.src = proxyUrl;
                        player.load();
                        player.play();
                    }
                } else {
                    // Load Standard MP4
                    player.src = proxyUrl;
                    player.load();
                    player.play();
                }
            }

            // Events
            searchBtn.onclick = executeSearch;
            searchInput.onkeydown = (e) => {
                if (e.key === 'Enter') executeSearch();
            };
            retrieveBtn.onclick = getSources;

            // Initial load
            executeSearch();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/proxy")
async def proxy_stream(url: str, request: Request):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Referer": "https://netfilm.world/",
        "Origin": "https://netfilm.world",
    }

    # If it is an SRT subtitle file, download, convert to VTT, and stream it
    if ".srt" in url.split("?")[0].lower():
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            try:
                resp = await client.get(url, headers=headers)
                
                # Try decoding with fallback charsets commonly used for subtitles
                content = ""
                for encoding in ["utf-8", "latin-1", "iso-8859-1", "cp1252"]:
                    try:
                        content = resp.content.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if not content:
                    content = resp.content.decode("utf-8", errors="ignore")

                # Perform SRT to VTT translation
                import re as _re
                import io as _io
                vtt_content = "WEBVTT\n\n" + content
                # Convert timestamps: 00:00:00,000 -> 00:00:00.000
                vtt_content = _re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", vtt_content)

                return StreamingResponse(
                    _io.BytesIO(vtt_content.encode("utf-8")),
                    media_type="text/vtt",
                    headers={"Access-Control-Allow-Origin": "*"}
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Subtitle conversion failed: {str(e)}")

    # Standard stream proxy (Range request support)
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60)
    try:
        req = client.build_request("GET", url, headers=headers)
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=500, detail=f"Proxy connection failed: {str(e)}")

    resp_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    }
    if resp.headers.get("content-range"):
        resp_headers["Content-Range"] = resp.headers["content-range"]
    if resp.headers.get("accept-ranges"):
        resp_headers["Accept-Ranges"] = resp.headers["accept-ranges"]
    if resp.headers.get("content-length"):
        resp_headers["Content-Length"] = resp.headers["content-length"]

    async def stream_generator():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "video/mp4"),
        headers=resp_headers
    )


@app.get("/home")
async def get_home():
    url = f"{API_BASE}/home?host=moviebox.ph"
    data = await _make_request(url)
    sections = []
    for op in data.get("data", {}).get("operatingList", []) or []:
        op_type = op.get("type")
        title = op.get("title", "Featured")
        if op_type == "BANNER":
            items = [{
                "name": item.get("title") or (item.get("subject") or {}).get("title"),
                "poster_url": item.get("image", {}).get("url") or (item.get("subject") or {}).get("cover", {}).get("url"),
                "slug": item.get("detailPath") or (item.get("subject") or {}).get("detailPath"),
                "subject_id": (item.get("subject") or {}).get("subjectId"),
                "badge": (item.get("subject") or {}).get("corner")
            } for item in op.get("banner", {}).get("items", []) if item.get("title") and "Communities" not in item.get("title")]
            sections.append({"section": "Banner", "count": len(items), "items": items})
        elif op_type in ["SUBJECTS_MOVIE", "SUBJECTS_TV", "SUBJECTS_ANIMATION"]:
            items = [{
                "name": sub.get("title"),
                "poster_url": sub.get("cover", {}).get("url"),
                "slug": sub.get("detailPath"),
                "subject_id": sub.get("subjectId"),
                "badge": sub.get("corner"),
                "rating": sub.get("imdbRatingValue")
            } for sub in op.get("subjects", [])]
            sections.append({"section": title, "count": len(items), "items": items})
    return {"status": "success", "sections": sections}

async def _get_category_data(tab_id: int, page: int = 1, per_page: int = 24, sort: str = "RECOMMEND") -> dict:
    url = f"{API_BASE}/subject/filter"
    payload = {"tabId": tab_id, "filter": {"sort": sort, "genre": "ALL", "country": "ALL", "year": "ALL", "language": "ALL"}, "page": page, "perPage": per_page}
    data = await _make_request(url, method="POST", payload=payload)
    inner = data.get("data", {})
    raw_items = inner.get("items", inner.get("subjects", []))
    items = [{
        "name": sub.get("title"),
        "poster_url": sub.get("cover", {}).get("url"),
        "slug": sub.get("detailPath"),
        "subject_id": sub.get("subjectId"),
        "badge": sub.get("corner"),
        "rating": sub.get("imdbRatingValue"),
        "year": sub.get("releaseDate", "")[:4] if sub.get("releaseDate") else None
    } for sub in raw_items]
    pager = inner.get("pager", {})
    total = pager.get("totalCount") or inner.get("total") or len(items)
    return {"page": page, "per_page": per_page, "total": total, "items": items}

@app.get("/movies")
async def get_movies(page: int = 1, sort: str = "RECOMMEND"):
    return await _get_category_data(tab_id=2, page=page, sort=sort)

@app.get("/tv-series")
async def get_tv_series(page: int = 1, sort: str = "RECOMMEND"):
    return await _get_category_data(tab_id=5, page=page, sort=sort)

@app.get("/animation")
async def get_animation(page: int = 1, sort: str = "RECOMMEND"):
    return await _get_category_data(tab_id=8, page=page, sort=sort)

@app.get("/search/suggest")
async def get_search_suggestions(q: str = Query(..., min_length=1)):
    url = f"{API_BASE}/subject/search-suggest"
    data = await _make_request(url, method="POST", payload={"keyword": q, "perPage": 10})
    inner = data.get("data", {})
    raw = inner.get("items", inner.get("list", []))
    suggestions = []
    for item in raw:
        sub = item.get("subject") or {}
        suggestions.append({
            "title": sub.get("title") or item.get("word") or item.get("title"),
            "slug": sub.get("detailPath") or item.get("detailPath"),
            "subject_id": sub.get("subjectId") or item.get("subjectId")
        })
    return {"suggestions": suggestions}

@app.get("/search")
async def search(q: str = Query(..., min_length=1), page: int = 1):
    url = f"{API_BASE}/subject/search"
    data = await _make_request(url, method="POST", payload={"keyword": q, "page": page, "perPage": 20})
    inner = data.get("data", {})
    raw = inner.get("items", inner.get("list", []))
    items = [{
        "name": sub.get("title"),
        "poster_url": sub.get("cover", {}).get("url"),
        "slug": sub.get("detailPath"),
        "subject_id": sub.get("subjectId")
    } for sub in raw]
    pager = inner.get("pager", {})
    total = pager.get("totalCount") or inner.get("total") or len(items)
    return {"query": q, "page": page, "total": total, "items": items}

@app.get("/detail/{slug}")
async def get_movie_detail(slug: str):
    url = f"{API_BASE}/detail?detailPath={slug}"
    return await _make_request(url)

@app.get("/api/stream/{subject_id}")
async def get_stream_sources(subject_id: str, detail_path: str, se: int = 1, ep: int = 1):
    # Step 1: get the player domain
    dom_data = await _make_request(f"{API_BASE}/media-player/get-domain")
    domain = dom_data.get("data", "https://netfilm.world").rstrip("/")

    # Step 2: build the Referer the way the real browser player does
    player_referer = (
        f"{domain}/spa/videoPlayPage/movies/{detail_path}"
        f"?id={subject_id}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
    )
    play_url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={subject_id}&se={se}&ep={ep}&detailPath={detail_path}"

    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        resp = await client.get(play_url, headers={**PLAYER_HEADERS, "Referer": player_referer})
        data = resp.json().get("data", {})

    has_resource = data.get("hasResource", False)
    streams = [
        {
            "resolution": f"{s.get('resolutions')}p",
            "format": s.get("format"),
            "url": s.get("url"),
            "size": s.get("size"),
            "duration": s.get("duration"),
            "codec": s.get("codecName")
        }
        for s in data.get("streams", [])
    ]
    return {
        "subject_id": subject_id,
        "se": se,
        "ep": ep,
        "has_resource": has_resource,
        "sources": streams,
        "hls": data.get("hls", []),
        "dash": data.get("dash", []),
        "free_episodes": data.get("freeNum"),
        "limited": data.get("limited", False),
        "note": None if has_resource else "No stream found for this episode."
    }

@app.get("/api/stream/{subject_id}/captions")
async def get_captions(subject_id: str, detail_path: str, se: int = 1, ep: int = 1):
    dom_data = await _make_request(f"{API_BASE}/media-player/get-domain")
    domain = dom_data.get("data", "https://netfilm.world").rstrip("/")

    player_referer = (
        f"{domain}/spa/videoPlayPage/movies/{detail_path}"
        f"?id={subject_id}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
    )
    play_url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={subject_id}&se={se}&ep={ep}&detailPath={detail_path}"

    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        play_resp = await client.get(play_url, headers={**PLAYER_HEADERS, "Referer": player_referer})
        play_data = play_resp.json().get("data", {})

    streams = play_data.get("streams", [])
    dash = play_data.get("dash", [])

    stream_id = None
    stream_format = None
    if streams:
        stream_id = streams[0].get("id")
        stream_format = streams[0].get("format", "MP4")
    elif dash:
        stream_id = dash[0].get("id")
        stream_format = dash[0].get("format", "DASH")

    if not stream_id:
        return {"subject_id": subject_id, "se": se, "ep": ep, "count": 0, "captions": []}

    cap_url = (
        f"{API_BASE}/subject/caption"
        f"?format={stream_format}&id={stream_id}&subjectId={subject_id}&detailPath={detail_path}"
    )
    data = await _make_request(cap_url)
    inner = data.get("data", {})
    captions = inner.get("captions", []) if isinstance(inner, dict) else inner
    return {"subject_id": subject_id, "se": se, "ep": ep, "count": len(captions), "captions": captions}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("newapi:app", host="0.0.0.0", port=8000, reload=True)
