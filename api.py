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

# Shared global AsyncClient for connection pooling and Keep-Alive reuse
http_client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()

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
    try:
        resp = await http_client.get(f"{API_BASE}/home?host=moviebox.ph", headers=DEFAULT_HEADERS)
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
    except Exception:
        pass
    return _bearer_token or ""

async def _make_request(url: str, method: str = "GET", payload: dict = None, custom_headers: dict = None) -> dict:
    global _bearer_token
    token = await _get_bearer_token()
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {token}" if token else "",
        **(custom_headers or {})
    }
    try:
        if method == "POST":
            resp = await http_client.post(url, headers=headers, json=payload)
        else:
            resp = await http_client.get(url, headers=headers)

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
        <title>MovieBox Pro | Developer Suite</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <!-- Media Players -->
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
                min-height: 100vh;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px 24px;
            }

            header {
                text-align: center;
                margin-bottom: 40px;
            }

            h1 {
                font-size: clamp(2rem, 5vw, 3.5rem);
                font-weight: 800;
                background: linear-gradient(135deg, #fff 0%, #aaa 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 5px;
                letter-spacing: -1px;
            }

            .badge {
                background: linear-gradient(90deg, var(--primary), var(--secondary));
                padding: 6px 14px;
                border-radius: 40px;
                font-size: 0.75rem;
                font-weight: 700;
                display: inline-block;
                margin-bottom: 15px;
                text-transform: uppercase;
                letter-spacing: 1px;
                box-shadow: 0 10px 30px rgba(255, 61, 113, 0.3);
            }

            /* Search Panel */
            .search-section {
                background: var(--card-bg);
                border: 1px solid var(--glass);
                padding: 25px;
                border-radius: 24px;
                backdrop-filter: blur(12px);
                margin-bottom: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }

            .search-bar {
                display: flex;
                gap: 12px;
            }

            .search-input {
                flex-grow: 1;
                background: rgba(0,0,0,0.5);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
                padding: 16px 20px;
                color: #fff;
                font-size: 1rem;
                font-family: inherit;
                outline: none;
                transition: all 0.3s;
            }

            .search-input:focus {
                border-color: var(--accent);
                box-shadow: 0 0 15px rgba(0,242,255,0.2);
            }

            .btn {
                background: #ffffff;
                color: #000000;
                border: none;
                border-radius: 14px;
                padding: 16px 30px;
                font-weight: 700;
                font-size: 1rem;
                font-family: inherit;
                cursor: pointer;
                transition: all 0.3s;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }

            .btn:hover {
                background: var(--primary);
                color: #fff;
                box-shadow: 0 10px 25px rgba(255, 61, 113, 0.4);
            }

            .btn-accent {
                background: var(--secondary);
                color: #fff;
            }

            .btn-accent:hover {
                background: var(--accent);
                color: #000;
                box-shadow: 0 10px 25px rgba(0,242,255,0.4);
            }

            /* Main Layout Grid */
            .main-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 30px;
            }

            @media (min-width: 900px) {
                .main-grid {
                    grid-template-columns: 350px 1fr;
                }
            }

            /* Panel Cards */
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

            /* Search Results */
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

            /* Details & Stream Controller */
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

            /* Stream Results */
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

            /* Player Area */
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
            }

            footer {
                text-align: center;
                padding: 40px 0 20px;
                font-size: 0.8rem;
                color: #444;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="badge">MovieBox Pro Developer Suite</div>
                <h1>Developer Playground & Testing Panel</h1>
            </header>

            <div class="search-section">
                <div class="search-bar">
                    <input type="text" id="searchInput" class="search-input" placeholder="Search movies, TV series, anime, or enter title..." value="Love Island USA">
                    <button class="btn btn-accent" id="searchBtn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        Search
                    </button>
                </div>
            </div>

            <div class="main-grid">
                <!-- Left panel: Search results -->
                <div class="panel">
                    <div class="panel-title">Search Results</div>
                    <div class="search-results" id="searchResults">
                        <!-- Items will be injected here -->
                        <div style="color: #666; text-align: center; padding: 20px;">Search for a title to begin</div>
                    </div>
                </div>

                <!-- Right panel: Controller & Player -->
                <div class="panel">
                    <div class="panel-title" id="controllerTitle">Stream Controller</div>
                    
                    <div id="mediaDetails" style="display: none;">
                        <div class="detail-card">
                            <div class="detail-header">
                                <img src="" id="detailPoster" class="detail-poster">
                                <div class="detail-header-info">
                                    <h2 id="detailTitle" class="detail-title"></h2>
                                    <div>
                                        <span class="rating" id="detailRating">★ -</span>
                                        <span class="tag" id="detailYear">-</span>
                                        <span class="tag" id="detailType">-</span>
                                    </div>
                                    <p id="detailDesc" style="color: #888; font-size: 0.9rem; line-height: 1.4; margin-top: 5px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;"></p>
                                </div>
                            </div>

                            <div class="selectors" id="seSelectorContainer">
                                <div class="select-group">
                                    <label for="seSelect">Season</label>
                                    <select id="seSelect"></select>
                                </div>
                                <div class="select-group">
                                    <label for="epSelect">Episode</label>
                                    <select id="epSelect"></select>
                                </div>
                            </div>

                            <button class="btn" id="retrieveBtn" style="margin-top: 10px;">Retrieve Streaming Sources</button>
                        </div>
                    </div>

                    <!-- Stream Sources & Player Section -->
                    <div id="sourcesSection" style="display: none;">
                        <div class="panel-title" style="margin-top: 30px; margin-bottom: 15px;">Available Stream Sources</div>
                        <div class="source-list" id="sourceList"></div>

                        <div class="panel-title" style="margin-top: 35px; margin-bottom: 15px;">Live Stream Testing Player</div>
                        <div class="player-container">
                            <div class="empty-player-placeholder" id="playerPlaceholder">
                                <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                Select a stream source to test playback
                            </div>
                            <video id="player" controls></video>
                        </div>
                    </div>
                </div>
            </div>

            <footer>
                Developer Panel built by walter &bull; Powered by FastAPI & Httpx
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
                    detailRating.textContent = `★ ${subject.imdbRate || 'N/A'}`;
                    detailYear.textContent = subject.releaseDate ? subject.releaseDate.substring(0, 4) : 'N/A';
                    detailType.textContent = subject.subjectType === 2 ? 'TV Show' : 'Movie';
                    detailDesc.textContent = subject.description || 'No description available.';

                    // Populate seasons dropdown if TV Show
                    const seasons = (detailData.resource && detailData.resource.seasons) || [];
                    if (subject.subjectType === 2 && seasons.length > 0) {
                        seSelectorContainer.style.display = 'grid';
                        seSelect.innerHTML = '';
                        
                        seasons.forEach(season => {
                            const option = document.createElement('option');
                            option.value = season.se;
                            option.textContent = `Season ${season.se}`;
                            seSelect.appendChild(option);
                        });

                        // Populate episodes based on selected season
                        seSelect.onchange = () => {
                            const selectedSe = seSelect.value;
                            const seasonConfig = seasons.find(s => s.se == selectedSe);
                            const maxEpisodes = seasonConfig ? seasonConfig.maxEp : 1;
                            
                            epSelect.innerHTML = '';
                            for (let i = 1; i <= maxEpisodes; i++) {
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
                        window.movieSe = seasons.length > 0 ? seasons[0].se : 0;
                        window.movieEp = seasons.length > 0 ? seasons[0].maxEp : 0;
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

    resp = await http_client.get(play_url, headers={**PLAYER_HEADERS, "Referer": player_referer})
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

    play_resp = await http_client.get(play_url, headers={**PLAYER_HEADERS, "Referer": player_referer})
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

async def _get_tmdb_metadata(tmdb_id: int, is_tv: bool) -> dict:
    url = f"https://api.themoviedb.org/3/{'tv' if is_tv else 'movie'}/{tmdb_id}?api_key=4ee9728210417b975a587e71f1b8e573"
    try:
        resp = await http_client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("name") if is_tv else data.get("title")
            orig_lang = data.get("original_language", "")
            genre_ids = [g.get("id") for g in data.get("genres", []) if isinstance(g, dict)]
            is_anime = orig_lang == "ja" or 16 in genre_ids
            return {"title": title, "original_language": orig_lang, "is_anime": is_anime}
    except Exception:
        pass
    return {"title": "", "original_language": "", "is_anime": False}

async def _resolve_subject(tmdb_id: int, is_tv: bool, lang: str | None = None):
    meta = await _get_tmdb_metadata(tmdb_id, is_tv)
    title = meta.get("title", "")
    is_anime = meta.get("is_anime", False)
    if not title:
        raise HTTPException(status_code=404, detail=f"TMDB ID {tmdb_id} not found")
        
    search_url = f"{API_BASE}/subject/search"
    
    # Special override for One Piece Netflix Live Action (TMDB ID: 111110)
    search_keyword = title
    if tmdb_id == 111110:
        search_keyword = "One Piece [netflix]"
        
    search_data = await _make_request(search_url, method="POST", payload={"keyword": search_keyword, "page": 1, "perPage": 20})
    raw_items = search_data.get("data", {}).get("items", [])
    if not raw_items:
        raise HTTPException(status_code=404, detail=f"No matches in MovieBox for TMDB title '{title}'")

    # Find the first item that doesn't have a language tag (prefer original)
    main_item = None
    for item in raw_items:
        title_lower = item.get("title", "").lower()
        
        # Skip Netflix live action when resolving anime
        if tmdb_id == 37854 and "netflix" in title_lower:
            continue
            
        # Require Netflix live action when resolving live action
        if tmdb_id == 111110 and "netflix" not in title_lower:
            continue
            
        has_lang_suffix = False
        for tag in ["tagalog", "english", "spanish", "french", "hindi", "dub"]:
            if f"[{tag}]" in title_lower or f"({tag})" in title_lower or title_lower.endswith(f" {tag}") or f" - {tag}" in title_lower:
                has_lang_suffix = True
                break
        if not has_lang_suffix:
            main_item = item
            break
    if not main_item:
        if tmdb_id == 37854:
            main_item = next((item for item in raw_items if "netflix" not in item.get("title", "").lower()), raw_items[0])
        elif tmdb_id == 111110:
            main_item = next((item for item in raw_items if "netflix" in item.get("title", "").lower()), raw_items[0])
        else:
            main_item = raw_items[0]

    subject_id = main_item.get("subjectId")
    slug = main_item.get("detailPath")
    
    if lang and lang.lower() not in ["ja", "original"]:
        lang = lang.lower()
        lang_names = {
            "en": "English",
            "english": "English",
            "tl": "Tagalog",
            "tagalog": "Tagalog",
            "es": "Spanish",
            "spanish": "Spanish",
            "fr": "French",
            "french": "French"
        }
        lang_name = lang_names.get(lang, lang)
        
        # 1. First, search for "Title + Language Name" to find the dedicated card using BFF POST API
        search_q = f"{search_keyword} {lang_name}"
        search_url = f"{API_BASE}/subject/search"
        search_data = await _make_request(
            search_url,
            method="POST",
            payload={"keyword": search_q, "page": 1, "perPage": 20}
        )
        inner = search_data.get("data", {})
        search_items = inner.get("items", inner.get("list", []))
            
        found_dub = False
        for item in search_items:
            item_title = item.get("title", "").lower()
            if tmdb_id == 111110 and "netflix" not in item_title:
                continue
            if tmdb_id == 37854 and "netflix" in item_title:
                continue
            if lang_name.lower() in item_title:
                subject_id = item.get("subjectId")
                slug = item.get("detailPath")
                found_dub = True
                break
                
        # 2. If not found via search, fallback to checking internal dubs list of the original card
        if not found_dub:
            detail_url = f"{API_BASE}/detail?detailPath={slug}"
            detail_data = await _make_request(detail_url)
            subject_info = detail_data.get("data", {}).get("subject", {})
            dubs_list = subject_info.get("dubs", [])
            for dub in dubs_list:
                if dub.get("lanCode", "").lower() == lang:
                    subject_id = dub.get("subjectId")
                    slug = dub.get("detailPath")
                    found_dub = True
                    break
                    
        # 3. If still not found, fallback to checking the initial search raw items
        if not found_dub:
            lang_markers = {
                "en": ["english", "dub"],
                "es": ["spanish", "español", "esla"],
                "tl": ["tagalog", "filipino"],
                "hi": ["hindi"],
                "tagalog": ["tagalog"],
                "english": ["english"]
            }
            markers = lang_markers.get(lang, [lang])
            for item in raw_items:
                name_lower = item.get("title", "").lower()
                if tmdb_id == 111110 and "netflix" not in name_lower:
                    continue
                if tmdb_id == 37854 and "netflix" in name_lower:
                    continue
                if any(m in name_lower for m in markers):
                    subject_id = item.get("subjectId")
                    slug = item.get("detailPath")
                    break

    detail_url = f"{API_BASE}/detail?detailPath={slug}"
    detail_data = await _make_request(detail_url)
    subject_info = detail_data.get("data", {}).get("subject", {})
    resource_info = detail_data.get("data", {}).get("resource", {})
    seasons = resource_info.get("seasons", [])
    
    dubs = []
    dubs.append({
        "language": "Original",
        "code": "original",
        "url": f"/tv/{tmdb_id}" if is_tv else f"/movie/{tmdb_id}"
    })
    for dub in subject_info.get("dubs", []):
        d_code = dub.get("lanCode")
        d_name = dub.get("lanName")
        if d_code:
            dubs.append({
                "language": d_name,
                "code": d_code,
                "url": (f"/tv/{tmdb_id}" if is_tv else f"/movie/{tmdb_id}") + f"/{d_code}"
            })
            
    return subject_id, slug, seasons, dubs, title, is_anime

async def handle_tv_stream(tmdb_id: int, season: int, episode: int, request: Request, lang: str | None = None, is_anime: bool = False):
    subject_id, slug, seasons, dubs, tmdb_title, is_anime_resolved = await _resolve_subject(tmdb_id, is_tv=True, lang=lang)
    is_anime = is_anime or is_anime_resolved
    
    # Map season to Moviebox season if it doesn't match
    se = season
    ep = episode
    
    # Ensure seasons list is in correct format and extract available season IDs
    available_seasons = []
    for s in seasons:
        if isinstance(s, dict):
            available_seasons.append(s.get("se"))
        elif isinstance(s, str) and "se=" in s:
            # Handle case where powershell or client receives string representations
            try:
                # E.g. "@{se=1; maxEp=1168; ...}"
                se_val = int(s.split("se=")[1].split(";")[0])
                available_seasons.append(se_val)
            except Exception:
                pass
            
    if season not in available_seasons and seasons:
        first_s = seasons[0]
        if isinstance(first_s, dict):
            se = first_s.get("se", 1)
        elif isinstance(first_s, str) and "se=" in first_s:
            try:
                se = int(first_s.split("se=")[1].split(";")[0])
            except Exception:
                se = 1
        else:
            se = 1

    stream_url = f"http://localhost:8000/api/stream/{subject_id}?detail_path={slug}&se={se}&ep={ep}"
    try:
        stream_resp = await http_client.get(stream_url)
        stream_data = stream_resp.json()
        
        # If no streams found and a custom dub language was requested, fall back to Japanese (Original)
        if not stream_data.get("sources") and not stream_data.get("hls") and not stream_data.get("dash") and lang and lang.lower() not in ["ja", "original"]:
            orig_subject_id, orig_slug, orig_seasons, _, _ = await _resolve_subject(tmdb_id, is_tv=True, lang=None)
            
            orig_se = season
            orig_available_seasons = []
            for s in orig_seasons:
                if isinstance(s, dict):
                    orig_available_seasons.append(s.get("se"))
                elif isinstance(s, str) and "se=" in s:
                    try:
                        orig_se_val = int(s.split("se=")[1].split(";")[0])
                        orig_available_seasons.append(orig_se_val)
                    except Exception:
                        pass
            if season not in orig_available_seasons and orig_seasons:
                first_s = orig_seasons[0]
                if isinstance(first_s, dict):
                    orig_se = first_s.get("se", 1)
                elif isinstance(first_s, str) and "se=" in first_s:
                    try:
                        orig_se = int(first_s.split("se=")[1].split(";")[0])
                    except Exception:
                        orig_se = 1
                else:
                    orig_se = 1

            stream_url = f"http://localhost:8000/api/stream/{orig_subject_id}?detail_path={orig_slug}&se={orig_se}&ep={episode}"
            stream_resp = await http_client.get(stream_url)
            stream_data = stream_resp.json()
            
            captions_url = f"http://localhost:8000/api/stream/{orig_subject_id}/captions?detail_path={orig_slug}&se={orig_se}&ep={episode}"
            captions_resp = await http_client.get(captions_url)
            captions_data = captions_resp.json()
        else:
            captions_url = f"http://localhost:8000/api/stream/{subject_id}/captions?detail_path={slug}&se={se}&ep={ep}"
            captions_resp = await http_client.get(captions_url)
            captions_data = captions_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streams: {str(e)}")

    base_url = str(request.base_url).rstrip("/")
    import urllib.parse
    sources = []
    
    for src in stream_data.get("sources", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": src.get("resolution"),
            "format": src.get("format"),
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })
    for src in stream_data.get("dash", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": f"{src.get('resolutions','Auto')}p",
            "format": "DASH",
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })
    for src in stream_data.get("hls", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": f"{src.get('resolutions','Auto')}p",
            "format": "HLS",
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })

    langMap = {
        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian',
        'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese', 'ja': 'Japanese',
        'ko': 'Korean', 'id': 'Indonesian', 'ms': 'Malay', 'th': 'Thai',
        'vi': 'Vietnamese', 'ar': 'Arabic', 'hi': 'Hindi', 'tl': 'Tagalog'
    }
    subtitles = []
    for cap in captions_data.get("captions", []):
        cap_url = cap.get("url")
        lan_code = cap.get("lan", "en").lower().split("_")[0]
        clean_label = langMap.get(lan_code, cap.get("lanName", "Subtitle"))
        subtitles.append({
            "label": clean_label,
            "srclang": lan_code,
            "url": cap_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(cap_url)}" if cap_url else ""
        })

    for d in dubs:
        prefix = f"/anime/{tmdb_id}/{season}/{episode}" if is_anime else f"/tv/{tmdb_id}/{season}/{episode}"
        d["url"] = prefix + (f"/{d['code']}" if d['code'] != "original" else "")

    return {
        "title": tmdb_title,
        "type": "anime" if is_anime else "tv",
        "tmdb_id": tmdb_id,
        "season": season,
        "episode": episode,
        "language": lang or "original",
        "subject_id": subject_id,
        "slug": slug,
        "sources": sources,
        "subtitles": subtitles,
        "dubs": dubs
    }

async def handle_movie_stream(tmdb_id: int, request: Request, lang: str | None = None):
    subject_id, slug, seasons, dubs, tmdb_title, _ = await _resolve_subject(tmdb_id, is_tv=False, lang=lang)
    
    se = seasons[0].get("se", 0) if seasons else 0
    ep = seasons[0].get("maxEp", 0) if seasons else 0
    
    stream_url = f"http://localhost:8000/api/stream/{subject_id}?detail_path={slug}&se={se}&ep={ep}"
    try:
        stream_resp = await http_client.get(stream_url)
        stream_data = stream_resp.json()
        
        captions_url = f"http://localhost:8000/api/stream/{subject_id}/captions?detail_path={slug}&se={se}&ep={ep}"
        captions_resp = await http_client.get(captions_url)
        captions_data = captions_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch streams: {str(e)}")

    base_url = str(request.base_url).rstrip("/")
    import urllib.parse
    sources = []
    
    for src in stream_data.get("sources", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": src.get("resolution"),
            "format": src.get("format"),
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })
    for src in stream_data.get("dash", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": f"{src.get('resolutions','Auto')}p",
            "format": "DASH",
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })
    for src in stream_data.get("hls", []):
        raw_url = src.get("url")
        sources.append({
            "resolution": f"{src.get('resolutions','Auto')}p",
            "format": "HLS",
            "url": raw_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(raw_url)}" if raw_url else ""
        })

    langMap = {
        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian',
        'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese', 'ja': 'Japanese',
        'ko': 'Korean', 'id': 'Indonesian', 'ms': 'Malay', 'th': 'Thai',
        'vi': 'Vietnamese', 'ar': 'Arabic', 'hi': 'Hindi', 'tl': 'Tagalog'
    }
    subtitles = []
    for cap in captions_data.get("captions", []):
        cap_url = cap.get("url")
        lan_code = cap.get("lan", "en").lower().split("_")[0]
        clean_label = langMap.get(lan_code, cap.get("lanName", "Subtitle"))
        subtitles.append({
            "label": clean_label,
            "srclang": lan_code,
            "url": cap_url,
            "proxy_url": f"{base_url}/api/proxy?url={urllib.parse.quote(cap_url)}" if cap_url else ""
        })

    for d in dubs:
        d["url"] = f"/movie/{tmdb_id}" + (f"/{d['code']}" if d['code'] != "original" else "")

    return {
        "title": tmdb_title,
        "type": "movie",
        "tmdb_id": tmdb_id,
        "language": lang or "original",
        "subject_id": subject_id,
        "slug": slug,
        "sources": sources,
        "subtitles": subtitles,
        "dubs": dubs
    }

@app.get("/anime/{tmdb_id}/{season}/{episode}")
async def get_anime_stream(tmdb_id: int, season: int, episode: int, request: Request):
    return await handle_tv_stream(tmdb_id, season, episode, request, is_anime=True)

@app.get("/anime/{tmdb_id}/{season}/{episode}/{lang}")
async def get_anime_stream_lang(tmdb_id: int, season: int, episode: int, lang: str, request: Request):
    return await handle_tv_stream(tmdb_id, season, episode, request, lang=lang, is_anime=True)

@app.get("/tv/{tmdb_id}/{season}/{episode}")
async def get_tv_stream(tmdb_id: int, season: int, episode: int, request: Request):
    return await handle_tv_stream(tmdb_id, season, episode, request, is_anime=False)

@app.get("/tv/{tmdb_id}/{season}/{episode}/{lang}")
async def get_tv_stream_lang(tmdb_id: int, season: int, episode: int, lang: str, request: Request):
    return await handle_tv_stream(tmdb_id, season, episode, request, lang=lang, is_anime=False)

@app.get("/movie/{tmdb_id}")
async def get_movie_stream(tmdb_id: int, request: Request):
    return await handle_movie_stream(tmdb_id, request)

@app.get("/movie/{tmdb_id}/{lang}")
async def get_movie_stream_lang(tmdb_id: int, lang: str, request: Request):
    return await handle_movie_stream(tmdb_id, request, lang=lang)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
