import os
import re
import json
import socket
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, send_from_directory
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

_DB_URL = os.getenv("DATABASE_URL", "")

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
        conn.commit()

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
    """Lazy-init DeepSeek client so missing key doesn't crash startup."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY environment variable is not set")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )


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


def fetch_transcript(video_id: str) -> tuple[list[dict], str]:
    """
    Fetch transcript with priority: zh > en > auto-generated.
    Returns (transcript_list, language_code).
    """
    api = YouTubeTranscriptApi()
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
        response = get_client().chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            timeout=60.0,
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
    BATCH_SIZE = 50           # smaller → model skips fewer lines per prompt
    MAX_WORKERS = 5           # lower → less risk of DeepSeek rate-limiting

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

    # Step 1: Extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Could not extract video ID from URL"}), 400

    # ── Cache hit: return instantly for previously-analyzed videos ──────────
    cached = _cache_get(video_id)
    if cached:
        return jsonify(cached)

    # Step 2: Fetch transcript
    try:
        raw_subtitles, lang = fetch_transcript(video_id)
    except TranscriptsDisabled:
        return jsonify({"error": "该视频没有可用字幕"}), 422
    except NoTranscriptFound:
        return jsonify({"error": "该视频没有可用字幕"}), 422
    except socket.timeout:
        return jsonify({"error": "字幕提取超时，请重试"}), 504
    except Exception as e:
        err = str(e).lower()
        if "timeout" in err or "timed out" in err:
            return jsonify({"error": "字幕提取超时，请重试"}), 504
        # Video unavailable / deleted / private / age-restricted → 422 with clean message
        unavailable_keywords = [
            "no longer available", "unavailable", "private", "does not exist",
            "video unavailable", "not available", "removed", "age-restricted",
        ]
        if any(kw in err for kw in unavailable_keywords):
            return jsonify({"error": "该视频不可用（可能已删除、设为私密或受年龄限制）"}), 422
        # Generic transcript error — return a short clean message, not the raw exception
        return jsonify({"error": "字幕提取失败，请确认视频存在且有字幕"}), 422

    # Steps 3 + 4: Translation and analysis run CONCURRENTLY ─────────────────
    #
    #  ┌─ build_bilingual_subtitles ─────── parallel batches ──┐
    #  │  (translate all subtitle lines)                        ├─ both finish
    #  └─ analyze_transcript ──────────────── single call ──────┘  together
    #
    # analyze_transcript uses raw_subtitles directly so it doesn't wait
    # for translation to complete first.

    bilingual_subtitles = None
    analysis = None
    error_response = None

    def _translate():
        return build_bilingual_subtitles(raw_subtitles, lang)

    def _analyze():
        return analyze_transcript(raw_subtitles)

    with ThreadPoolExecutor(max_workers=2) as pool:
        ft = pool.submit(_translate)
        fa = pool.submit(_analyze)

        # Collect translation result
        try:
            bilingual_subtitles = ft.result()
        except TimeoutError as e:
            error_response = (jsonify({"error": str(e)}), 504)
        except ValueError as e:
            error_response = (jsonify({"error": str(e)}), 401)
        except Exception as e:
            error_response = (jsonify({"error": f"翻译失败：{str(e)}"}), 500)

        # Collect analysis result
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

    # Step 5: Build, cache, and return full response
    response_data = {
        "videoId": video_id,
        "subtitles": bilingual_subtitles,
        "analysis": analysis,
    }
    _cache_set(video_id, response_data)
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
