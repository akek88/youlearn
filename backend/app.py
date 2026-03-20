import os
import re
import json
import socket
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from openai import OpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
CORS(app, origins="*")

# ── History DB (PostgreSQL via Railway DATABASE_URL) ─────────────────────────
import psycopg2
import psycopg2.extras

# Railway provides "postgres://" but psycopg2 requires "postgresql://"
_DB_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)

def _db():
    conn = psycopg2.connect(_DB_URL)
    return conn

def _init_db():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    user_id    TEXT NOT NULL,
                    video_id   TEXT NOT NULL,
                    url        TEXT NOT NULL,
                    theme      TEXT NOT NULL DEFAULT '',
                    watched_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, video_id)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS video_cache (
                    video_id   TEXT PRIMARY KEY,
                    data       JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            ''')
        conn.commit()


def _db_cache_get(video_id: str) -> dict | None:
    if not _DB_URL:
        return None
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM video_cache WHERE video_id = %s", (video_id,))
                row = cur.fetchone()
        if row:
            return row[0]  # psycopg2 auto-parses JSONB to dict
    except Exception as e:
        print(f"[db_cache_get] error: {e}", flush=True)
    return None


def _db_cache_set(video_id: str, data: dict) -> None:
    if not _DB_URL:
        return
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO video_cache (video_id, data)
                       VALUES (%s, %s::jsonb)
                       ON CONFLICT (video_id) DO UPDATE SET
                           data = EXCLUDED.data,
                           created_at = NOW()''',
                    (video_id, json.dumps(data))
                )
            conn.commit()
    except Exception as e:
        print(f"[db_cache_set] error: {e}", flush=True)

if _DB_URL:
    _init_db()


# ── In-memory result cache (video_id → full response dict) ──────────────────
# Survives for the lifetime of the process; cleared on redeploy.
# Keeps the last CACHE_MAX videos so memory stays bounded.
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_MAX = 60

def _cache_get(video_id: str) -> dict | None:
    with _cache_lock:
        return _cache.get(video_id)

def _cache_set(video_id: str, data: dict) -> None:
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            oldest = next(iter(_cache))
            del _cache[oldest]
        _cache[video_id] = data


def get_client():
    """Lazy-init OpenRouter client."""
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")
    base_url = "https://openrouter.ai/api/v1" if os.getenv("OPENROUTER_API_KEY") else "https://api.deepseek.com"
    return OpenAI(api_key=api_key, base_url=base_url)


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def snippets_to_dicts(snippets) -> list[dict]:
    """Convert FetchedTranscriptSnippet objects to plain dicts."""
    return [{"start": s.start, "duration": s.duration, "text": s.text} for s in snippets]


def _make_transcript_api() -> YouTubeTranscriptApi:
    """Return a YouTubeTranscriptApi instance, injecting YouTube cookies if available."""
    from requests import Session
    import http.cookiejar

    cookies_content = os.getenv("YOUTUBE_COOKIES", "").strip()
    session = Session()
    session.headers.update({"Accept-Language": "en-US"})

    if cookies_content:
        # Railway may encode newlines as literal \n — restore them
        cookies_content = cookies_content.replace('\\n', '\n')
        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.write(cookies_content)
        tmp.close()
        try:
            jar = http.cookiejar.MozillaCookieJar(tmp.name)
            jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = jar
            print(f"[cookies] loaded {len(list(jar))} cookies from cookie file", flush=True)
        except Exception as ce:
            print(f"[cookies] failed to load cookies: {ce}", flush=True)
    else:
        print("[cookies] no YOUTUBE_COOKIES env var set", flush=True)

    return YouTubeTranscriptApi(http_client=session)


def fetch_transcript(video_id: str) -> tuple[list[dict], str]:
    """
    Fetch transcript with priority: zh > en > auto-generated.
    Returns (transcript_list, language_code).
    """
    api = _make_transcript_api()
    transcript_list = api.list(video_id)

    # Priority 1: manual Chinese
    try:
        transcript = transcript_list.find_manually_created_transcript(["zh-TW", "zh-CN", "zh"])
        return snippets_to_dicts(transcript.fetch()), "zh"
    except NoTranscriptFound:
        pass

    # Priority 2: manual English
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
        return snippets_to_dicts(transcript.fetch()), "en"
    except NoTranscriptFound:
        pass

    # Priority 3: auto-generated Chinese
    try:
        transcript = transcript_list.find_generated_transcript(["zh-TW", "zh-CN", "zh"])
        return snippets_to_dicts(transcript.fetch()), "zh"
    except NoTranscriptFound:
        pass

    # Priority 4: auto-generated English
    try:
        transcript = transcript_list.find_generated_transcript(["en"])
        return snippets_to_dicts(transcript.fetch()), "en"
    except NoTranscriptFound:
        pass

    # Fallback: take whatever is available
    for t in transcript_list:
        return snippets_to_dicts(t.fetch()), t.language_code

    raise NoTranscriptFound(video_id, [], [])


def parse_json_response(raw: str) -> dict | list:
    """Strip code fences and parse JSON from AI response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw.strip())


def deepseek_generate(prompt: str) -> str:
    """Call DeepSeek and return response text, with error mapping."""
    try:
        model = "qwen/qwen-2.5-72b-instruct" if os.getenv("OPENROUTER_API_KEY") else "deepseek-chat"
        response = get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=120.0,
        )
        return response.choices[0].message.content
    except AuthenticationError:
        raise ValueError("DeepSeek API Key 无效，请检查 backend/.env 中的 DEEPSEEK_API_KEY")
    except RateLimitError:
        raise ValueError("DeepSeek API 配额已用完，请稍后重试")
    except APITimeoutError:
        raise TimeoutError("DeepSeek API 请求超时，请重试")
    except APIConnectionError:
        raise TimeoutError("DeepSeek API 连接失败，请检查网络后重试")
    except Exception as e:
        err = str(e).lower()
        if "timeout" in err or "timed out" in err:
            raise TimeoutError("DeepSeek API 请求超时，请重试")
        if "api key" in err or "authentication" in err or "unauthorized" in err:
            raise ValueError("DeepSeek API Key 无效，请检查 backend/.env 中的 DEEPSEEK_API_KEY")
        raise


def translate_batch(batch: list[dict], offset: int) -> dict:
    """Translate one batch; returns {line_number: zh_string} dict.

    Using a numbered JSON *object* (not array) so that even if the model
    returns fewer items or reorders them, each translation maps back to the
    correct subtitle via its explicit key.
    """
    lines = "\n".join(
        f"{offset + i + 1}. {s['text'].strip()}" for i, s in enumerate(batch)
    )
    prompt = (
        "Please translate the following numbered English subtitle lines into Chinese. "
        "Return ONLY a JSON object where each key is the line number (as a string) "
        "and each value is the Chinese translation. "
        "Example format: {\"1\": \"你好世界\", \"2\": \"如何工作\"}. "
        "Do NOT include the number inside the value. No extra commentary.\n\n"
        f"{lines}"
    )
    raw = deepseek_generate(prompt)

    def _strip_num(s: str) -> str:
        """Remove any accidental leading number prefix like '316. '"""
        return re.sub(r'^\d+[\.\s]+', '', str(s).strip())

    try:
        parsed = parse_json_response(raw)
        if isinstance(parsed, dict):
            return {int(k): _strip_num(v) for k, v in parsed.items()}
        if isinstance(parsed, list):
            # Model returned array despite instructions — map positionally
            return {offset + i + 1: _strip_num(v) for i, v in enumerate(parsed)}
    except (json.JSONDecodeError, ValueError):
        pass

    # Last resort: scrape numbered lines from plain text
    result = {}
    for m in re.finditer(r'^(\d+)[.\s]+(.+)$', raw, re.MULTILINE):
        result[int(m.group(1))] = _strip_num(m.group(2).strip('"'))
    return result


def translate_subtitles(subtitles: list[dict]) -> list[dict]:
    """Translate English subtitles to Chinese — parallel batches + retry pass for gaps.

    Two-phase strategy:
      Phase 1 – Fire all batches in parallel (lower concurrency to avoid rate limits).
                 BATCH_SIZE=50 keeps prompts short so the model rarely skips lines.
                 MAX_WORKERS=5 avoids DeepSeek rate-limit errors that silently drop
                 entire batches.
      Phase 2 – Collect every line number absent from zh_map and re-translate in
                 fresh batches using the actual original line numbers as keys, so the
                 returned JSON maps directly back without positional ambiguity.
    """
    BATCH_SIZE = 100          # larger batches → fewer API calls → faster overall
    MAX_WORKERS = 10          # more parallelism → faster translation

    batches = [
        (i, subtitles[i:i + BATCH_SIZE])
        for i in range(0, len(subtitles), BATCH_SIZE)
    ]

    zh_map: dict = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
        future_to_offset = {
            pool.submit(translate_batch, batch, offset): offset
            for offset, batch in batches
        }
        for future in as_completed(future_to_offset):
            try:
                zh_map.update(future.result())
            except Exception:
                pass  # batch failed; missing lines caught by retry pass below

    # ── Retry pass ────────────────────────────────────────────────────────────
    # Any line number absent from zh_map gets re-sent using its *actual* 1-based
    # line number so the returned JSON keys always match zh_map keys exactly.

    def _strip_num_retry(s: str) -> str:
        """Remove accidental leading number prefix like '48. '."""
        return re.sub(r'^\d+[\.\s]+', '', str(s).strip())

    def _parse_retry_response(raw: str, chunk: list) -> dict:
        """Parse retry API response into {line_num: zh_text} dict."""
        try:
            parsed = parse_json_response(raw)
            if isinstance(parsed, dict):
                return {int(k): _strip_num_retry(v) for k, v in parsed.items()}
            if isinstance(parsed, list):
                return {chunk[j][0]: _strip_num_retry(v)
                        for j, v in enumerate(parsed) if j < len(chunk)}
        except (json.JSONDecodeError, ValueError):
            pass
        # Last resort: scrape numbered lines from plain text
        result = {}
        for m in re.finditer(r'^(\d+)[.\s]+(.+)$', raw, re.MULTILINE):
            result[int(m.group(1))] = _strip_num_retry(m.group(2).strip('"'))
        return result

    missing = [
        (i + 1, subtitles[i]["text"].strip())
        for i in range(len(subtitles))
        if (i + 1) not in zh_map
    ]

    if missing:
        for chunk_start in range(0, len(missing), BATCH_SIZE):
            chunk = missing[chunk_start:chunk_start + BATCH_SIZE]
            lines = "\n".join(f"{ln}. {text}" for ln, text in chunk)
            prompt = (
                "Please translate the following numbered English subtitle lines into Chinese. "
                "Return ONLY a JSON object where each key is the line number (as a string) "
                "and each value is the Chinese translation. "
                "Example format: {\"1\": \"你好世界\", \"2\": \"如何工作\"}. "
                "Do NOT include the number inside the value. No extra commentary.\n\n"
                f"{lines}"
            )
            try:
                raw = deepseek_generate(prompt)
                zh_map.update(_parse_retry_response(raw, chunk))
            except Exception:
                pass  # accept empty zh for lines that still can't be translated

    # ── Build final result ────────────────────────────────────────────────────
    result = []
    for i, s in enumerate(subtitles):
        line_num = i + 1
        en_text = s["text"].strip()
        zh = zh_map.get(line_num, "")
        # Guard: if translation missing or identical to English, leave zh blank
        # so the UI never shows "double English" for an untranslated line.
        if not zh or zh.strip() == en_text:
            zh = ""
        result.append({
            "start": s["start"],
            "duration": s["duration"],
            "en": en_text,
            "zh": zh,
        })
    return result


def build_bilingual_subtitles(subtitles: list[dict], lang: str) -> list[dict]:
    """Return subtitle list in bilingual format."""
    if lang == "zh":
        return [
            {
                "start": s["start"],
                "duration": s["duration"],
                "en": "",
                "zh": s["text"].strip(),
            }
            for s in subtitles
        ]
    # English — translate to Chinese (parallel batches)
    return translate_subtitles(subtitles)


def analyze_transcript(subtitles: list[dict]) -> dict:
    """Send first 200 subtitles to DeepSeek for structured analysis.

    Accepts both raw subtitles (key 'text') and bilingual dicts
    (keys 'en'/'zh') so it can run concurrently with translation.
    """
    sample = subtitles[:200]
    full_text = " ".join(
        (s.get("zh") or s.get("en") or s.get("text", "")).strip()
        for s in sample
    )

    prompt = (
        "You are an expert learning assistant. Analyze the following video transcript "
        "and return a JSON object with exactly these four keys:\n"
        "- \"theme\": a concise core theme written in both Chinese and English, "
        "  e.g. \"机器学习基础 / Introduction to Machine Learning\"\n"
        "- \"keyPoints\": an array of 5-8 key knowledge points (in Chinese)\n"
        "- \"insights\": an array of 3-5 deeper insights or takeaways (in Chinese)\n"
        "- \"further\": an array of 3-5 suggested further reading topics or resources (in Chinese)\n\n"
        "Return ONLY the raw JSON object, no markdown fences, no extra text.\n\n"
        f"Transcript:\n{full_text}"
    )

    raw = deepseek_generate(prompt)

    try:
        return parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return {
            "theme": "分析结果解析失败 / Analysis Parse Error",
            "keyPoints": [raw[:300]] if raw else ["无法解析分析结果"],
            "insights": [],
            "further": [],
        }


@app.route("/api/history", methods=["GET", "POST", "DELETE"])
def history_route():
    if not _DB_URL:
        return jsonify([]) if request.method == "GET" else jsonify({"ok": True})

    if request.method == "GET":
        user_id = request.args.get("user_id", "").strip()
        if not user_id:
            return jsonify([])
        with _db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT video_id, url, theme, watched_at FROM history "
                    "WHERE user_id = %s ORDER BY watched_at DESC LIMIT 20",
                    (user_id,)
                )
                rows = cur.fetchall()
        return jsonify([
            {"videoId": r["video_id"], "url": r["url"],
             "theme": r["theme"], "watchedAt": r["watched_at"]}
            for r in rows
        ])

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        user_id  = data.get("user_id",  "").strip()
        video_id = data.get("video_id", "").strip()
        url      = data.get("url",      "").strip()
        theme    = data.get("theme",    "").strip()
        if not user_id or not video_id:
            return jsonify({"error": "Missing user_id or video_id"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO history (user_id, video_id, url, theme, watched_at)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (user_id, video_id) DO UPDATE SET
                           url        = EXCLUDED.url,
                           theme      = EXCLUDED.theme,
                           watched_at = EXCLUDED.watched_at''',
                    (user_id, video_id, url, theme, now)
                )
            conn.commit()
        return jsonify({"ok": True})

    # DELETE
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history WHERE user_id = %s", (user_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    url = data["url"].strip()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Could not extract video ID from URL"}), 400

    # ── In-memory cache hit ──────────────────────────────────────────────────
    mem_cached = _cache_get(video_id)
    if mem_cached:
        return jsonify(mem_cached)

    # ── DB cache hit (persists across redeploys) ─────────────────────────────
    db_cached = _db_cache_get(video_id)
    if db_cached:
        _cache_set(video_id, db_cached)
        return jsonify(db_cached)

    # ── Fetch transcript ─────────────────────────────────────────────────────
    try:
        raw_subtitles, lang = fetch_transcript(video_id)
    except TranscriptsDisabled:
        return jsonify({"error": "该视频没有可用字幕"}), 422
    except NoTranscriptFound:
        return jsonify({"error": "该视频没有可用字幕"}), 422
    except socket.timeout:
        return jsonify({"error": "字幕提取超时，请重试"}), 504
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = str(e).lower()
        if "timeout" in err or "timed out" in err:
            return jsonify({"error": "字幕提取超时，请重试"}), 504
        unavailable_keywords = ["no longer available", "unavailable", "private",
                                 "does not exist", "video unavailable",
                                 "not available", "removed", "age-restricted"]
        if any(kw in err for kw in unavailable_keywords):
            return jsonify({"error": "该视频不可用（可能已删除、设为私密或受年龄限制）"}), 422
        return jsonify({"error": f"字幕提取失败: {type(e).__name__}: {str(e)[:200]}"}), 422

    # ── Translation + analysis (concurrent) ──────────────────────────────────
    bilingual_subtitles = None
    analysis = None
    error_response = None

    with ThreadPoolExecutor(max_workers=2) as pool:
        ft = pool.submit(build_bilingual_subtitles, raw_subtitles, lang)
        fa = pool.submit(analyze_transcript, raw_subtitles)

        try:
            bilingual_subtitles = ft.result()
        except TimeoutError as e:
            error_response = (jsonify({"error": str(e)}), 504)
        except ValueError as e:
            error_response = (jsonify({"error": str(e)}), 401)
        except Exception as e:
            error_response = (jsonify({"error": f"翻译失败：{str(e)}"}), 500)

        try:
            analysis = fa.result()
        except TimeoutError as e:
            if not error_response:
                error_response = (jsonify({"error": str(e)}), 504)
        except ValueError as e:
            if not error_response:
                error_response = (jsonify({"error": str(e)}), 401)
        except Exception as e:
            if not error_response:
                error_response = (jsonify({"error": f"分析失败：{str(e)}"}), 500)

    if error_response:
        return error_response

    # ── Cache and return ─────────────────────────────────────────────────────
    response_data = {"videoId": video_id, "subtitles": bilingual_subtitles, "analysis": analysis}
    _cache_set(video_id, response_data)
    _db_cache_set(video_id, response_data)
    return jsonify(response_data)


# ── Static file serving (production: Flask hosts the built frontend) ──
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'dist')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and os.path.exists(os.path.join(DIST_DIR, path)):
        return send_from_directory(DIST_DIR, path)
    return send_from_directory(DIST_DIR, 'index.html')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
