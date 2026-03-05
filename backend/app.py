import os
import re
import json
import socket
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from openai import OpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
CORS(app, origins="*")

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
    """Translate English subtitle entries to Chinese using DeepSeek (batched)."""
    BATCH_SIZE = 50
    zh_map: dict = {}  # {1-based line number → zh string}

    for i in range(0, len(subtitles), BATCH_SIZE):
        batch = subtitles[i:i + BATCH_SIZE]
        zh_map.update(translate_batch(batch, i))

    result = []
    for i, s in enumerate(subtitles):
        line_num = i + 1
        result.append({
            "start": s["start"],
            "duration": s["duration"],
            "en": s["text"].strip(),
            "zh": zh_map.get(line_num, s["text"].strip()),
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
    # English — translate to Chinese
    return translate_subtitles(subtitles)


def analyze_transcript(subtitles: list[dict]) -> dict:
    """Send first 200 subtitles to DeepSeek for structured analysis."""
    sample = subtitles[:200]
    full_text = " ".join(
        (s.get("zh") or s.get("en", "")).strip() for s in sample
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
        return jsonify({"error": f"字幕提取失败：{str(e)}"}), 500

    # Step 3: Build bilingual subtitles (translate if English)
    try:
        bilingual_subtitles = build_bilingual_subtitles(raw_subtitles, lang)
    except TimeoutError as e:
        return jsonify({"error": str(e)}), 504
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        return jsonify({"error": f"翻译失败：{str(e)}"}), 500

    # Step 4: Analyze transcript with DeepSeek
    try:
        analysis = analyze_transcript(bilingual_subtitles)
    except TimeoutError as e:
        return jsonify({"error": str(e)}), 504
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        return jsonify({"error": f"分析失败：{str(e)}"}), 500

    # Step 5: Return full response
    return jsonify({
        "videoId": video_id,
        "subtitles": bilingual_subtitles,
        "analysis": analysis,
    })


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
