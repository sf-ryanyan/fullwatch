#!/usr/bin/env python3
"""Fullwatch: read the FULL transcript of a video, token-efficiently, never guess.

Works in the Claude chat app (the user supplies the transcript) and in Claude Code
(captions fetched automatically with yt-dlp). Standard library only. Optional:
faster-whisper for videos without captions (reuses models downloaded by Buzz).

Commands (every command prints JSON):
  doctor [--init]          check tools, models and config
  fetch URL                captions -> clean transcript (no video download)
  transcribe URL|FILE      local faster-whisper transcription (no captions)
  import FILE [--url URL]  a transcript the user supplied: YouTube "Show transcript"
                           copy, SRT, VTT or TXT
  coverage NOTES ID        check that the notes cover 00:00 -> end
  quotes NOTES ID          check that every 「quote」 exists in the transcript
  find QUERY               search videos and notes already saved
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION = "1.1.0"
SKILL_DIR = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("FULLWATCH_HOME") or Path.home() / ".cache" / "fullwatch")
CONFIG_PATH = Path(os.environ.get("FULLWATCH_CONFIG") or Path.home() / ".config" / "fullwatch" / "config.json")
IS_WINDOWS = platform.system() == "Windows"
ZH_PROMPT = "以下是普通话内容，使用简体中文，并加上标点符号。"


# ---------------------------------------------------------------- config

def buzz_model_dir() -> Path:
    """Where the Buzz desktop app keeps its models (reused, never modified)."""
    system = platform.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / "Buzz" / "Buzz" / "Cache"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Caches" / "Buzz"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "Buzz"
    return base / "models"


CHAT_OUTPUTS = Path("/mnt/user-data/outputs")  # downloadable-files folder in the Claude chat sandbox


def default_notes_dir() -> str:
    if CHAT_OUTPUTS.is_dir():
        return str(CHAT_OUTPUTS)
    return str(Path.home() / "Documents" / "fullwatch-notes")


DEFAULTS = {
    "caption_langs": [],          # preferred caption languages; empty = original language first
    "notes_dir": default_notes_dir(),
    "output_language": "zh",      # notes language; Chinese by default
    "lens": "",                   # the user's field, used for the "takeaways" section
    "block_seconds": 45,          # one transcript line per ~45 s of speech
    "part_minutes": 15,           # long videos are split into parts of ~15 min
    "whisper": {
        "model": "small",         # GPU model; "medium" is more accurate for Chinese
        "cpu_model": "small",     # model used when falling back to CPU
        "model_dir": "",          # empty = Buzz model folder if present
        "device": "auto",         # auto | cuda | cpu
        "language": "",           # e.g. "zh" or "en"; empty = auto-detect
        "initial_prompt": "",     # empty = a default simplified-Chinese prompt for zh
        "vad": True,              # skip silence
        "buzz_dir": "",           # Buzz install folder, e.g. F:\\Buzz; its CUDA DLLs are reused for the GPU
        "cuda_dll_dirs": [],      # extra folders containing cublas64_12.dll / cudnn DLLs (Windows)
    },
}

BUZZ_INSTALL_GUESSES = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Buzz",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Buzz",
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "Buzz",
] + ([Path(f"{letter}:\\Buzz") for letter in "CDEFGHIJ"] if IS_WINDOWS else [])  # e.g. F:\Buzz
_DLL_DIRS_ADDED: list = []


def add_cuda_dll_dirs(cfg: dict) -> list:
    """Windows: let ctranslate2 find cuBLAS / cuDNN without a separate CUDA install.

    Looks in (1) folders listed in the config, (2) the Buzz install (it bundles the
    NVIDIA runtime under _internal/nvidia), (3) pip 'nvidia-*' packages in site-packages.
    """
    if not IS_WINDOWS or not hasattr(os, "add_dll_directory") or _DLL_DIRS_ADDED:
        return _DLL_DIRS_ADDED
    w = cfg["whisper"]
    found = [Path(os.path.expanduser(p)) for p in w.get("cuda_dll_dirs") or []]
    buzz_roots = ([Path(os.path.expanduser(w["buzz_dir"]))] if w.get("buzz_dir") else []) + BUZZ_INSTALL_GUESSES
    roots = [r / "_internal" for r in buzz_roots] + [Path(p) for p in sys.path if p.endswith("site-packages")]
    for root in roots:
        nvidia = root / "nvidia"
        if nvidia.is_dir():
            for pkg in nvidia.iterdir():
                for sub in ("bin", "lib"):
                    if (pkg / sub).is_dir():
                        found.append(pkg / sub)
    for d in found:
        if d.is_dir() and str(d) not in _DLL_DIRS_ADDED:
            try:
                os.add_dll_directory(str(d))
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
                _DLL_DIRS_ADDED.append(str(d))
            except OSError:
                pass
    return _DLL_DIRS_ADDED


def av_hint():
    """faster-whisper 1.2.x passes an argument that newer PyAV releases removed."""
    try:
        import av
        major = int(str(av.__version__).split(".")[0])
    except Exception:
        return None
    if major >= 16:
        return (f"PyAV {av.__version__} may not work with this faster-whisper. If transcription fails with "
                "'metadata_errors', run: python -m pip install \"av<16\"")
    return None


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.is_file():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise SystemExit(emit({"status": "config_error", "message": f"{CONFIG_PATH}: {exc}"}, 2))
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    if not cfg["whisper"].get("model_dir"):
        buzz = buzz_model_dir()
        cfg["whisper"]["model_dir"] = str(buzz if buzz.is_dir() else HOME / "models")
    return cfg


# ---------------------------------------------------------------- helpers

def emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    return code


def fmt_time(sec) -> str:
    sec = int(round(max(0.0, float(sec or 0))))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_clock(text: str):
    parts = text.strip().replace(",", ".").split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([A-Za-z0-9_-]{11})")


def video_id(text: str):
    text = text.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = ID_RE.search(text)
    return m.group(1) if m else None


CJK_RE = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")


def est_tokens(text: str) -> int:
    """Rough token estimate: ~1.2 per CJK character, ~1 per 3.8 other characters."""
    cjk = len(CJK_RE.findall(text))
    return int(cjk * 1.2 + (len(text) - cjk) / 3.8)


def join_text(a: str, b: str) -> str:
    if not a:
        return b
    if CJK_RE.match(a[-1]) or CJK_RE.match(b[0]):
        # Chinese captions often lack punctuation: keep a space so phrases stay readable
        return a + b if a[-1] in "，。！？、；：,.!?;:）」』" else a + " " + b
    return a + " " + b


def run(cmd: list, timeout: int = 600):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def vdir(vid: str) -> Path:
    d = HOME / "videos" / vid
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_meta(vid: str):
    p = HOME / "videos" / vid / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ---------------------------------------------------------------- yt-dlp

def ytdlp_hint() -> str:
    if IS_WINDOWS:
        return "winget install --id yt-dlp.yt-dlp --exact   (or: python -m pip install -U yt-dlp)"
    if platform.system() == "Darwin":
        return "brew install yt-dlp   (or: python3 -m pip install -U yt-dlp)"
    return "python3 -m pip install -U yt-dlp"


def ytdlp_base(args):
    exe = shutil.which("yt-dlp")
    if exe:
        cmd = [exe]
    else:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            return None
        cmd = [sys.executable, "-m", "yt_dlp"]
    cmd += ["--no-warnings", "--no-playlist"]
    if getattr(args, "cookies_from_browser", None):
        cmd += ["--cookies-from-browser", args.cookies_from_browser]
    if getattr(args, "cookies", None):
        cmd += ["--cookies", args.cookies]
    return cmd


def classify(stderr: str) -> str:
    s = stderr.lower()
    if any(k in s for k in ("sign in to confirm", "not a bot", "http error 429", "http error 403")):
        return "blocked"
    if any(k in s for k in ("private video", "video unavailable", "has been removed",
                            "members-only", "not available", "this live event")):
        return "unavailable"
    if any(k in s for k in ("unable to download webpage", "name resolution", "timed out",
                            "connection", "getaddrinfo")):
        return "network"
    return "error"


def last_error(stderr: str) -> str:
    lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    errs = [l for l in lines if "ERROR" in l]
    return (errs or lines or ["unknown error"])[-1][:400]


def failure(stderr: str) -> dict:
    status = classify(stderr)
    hint = {
        "blocked": "Update yt-dlp and retry once. If it persists, add --cookies-from-browser chrome (or firefox/edge).",
        "unavailable": "The video is private, removed, members-only or region-locked.",
        "network": "Check the internet connection, then retry.",
    }.get(status, "See message.")
    return {"status": status, "message": last_error(stderr), "hint": hint}


def get_info(url: str, d: Path, args):
    base = ytdlp_base(args)
    if base is None:
        return None, {"status": "needs_ytdlp", "hint": ytdlp_hint()}
    code, out, err = run(base + ["-J", "--skip-download", url], timeout=180)
    if code != 0 or not out.strip():
        return None, failure(err)
    try:
        info = json.loads(out)
    except json.JSONDecodeError:
        return None, {"status": "error", "message": "yt-dlp returned unreadable metadata"}
    (d / "info.json").write_text(out, encoding="utf-8")
    return info, None


def pick_track(info: dict, prefs: list):
    """Choose ONE real caption track: manual first, then the original auto track."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat" and v}
    auto = {k: v for k, v in (info.get("automatic_captions") or {}).items() if v}
    orig = (info.get("language") or "").strip()

    def find(pool, langs):
        for lang in langs:
            if lang in pool:
                return lang
        for lang in langs:
            base = lang.split("-")[0].lower()
            for key in pool:
                if key.split("-")[0].lower() == base and not key.endswith("-orig"):
                    return key
        return None

    langs = list(prefs) + ([orig] if orig else [])
    key = find(manual, langs) or (next(iter(manual)) if manual else None)
    if key:
        return {"kind": "manual", "key": key, "translated": False}
    origs = [k for k in auto if k.endswith("-orig")]
    if origs:
        same = [k for k in origs if orig and k.split("-")[0] == orig.split("-")[0]]
        return {"kind": "auto", "key": (same or origs)[0], "translated": False}
    if orig and orig in auto:
        return {"kind": "auto", "key": orig, "translated": False}
    key = find(auto, list(prefs) or ["en"])
    if key:
        return {"kind": "auto", "key": key, "translated": None}  # may be a machine translation
    return None


def download_subs(d: Path, track: dict, args):
    for f in d.glob("subs.*"):
        f.unlink()
    base = ytdlp_base(args)
    flag = "--write-subs" if track["kind"] == "manual" else "--write-auto-subs"
    cmd = base + ["--load-info-json", str(d / "info.json"), "--skip-download", flag,
                  "--sub-langs", re.escape(track["key"]), "--sub-format", "json3/vtt/srt/best",
                  "-o", str(d / "subs.%(ext)s")]
    code, out, err = run(cmd, timeout=180)
    files = [f for f in sorted(d.glob("subs.*")) if f.suffix.lower() in (".json3", ".vtt", ".srt")]
    if not files:
        return None, failure(err or "no caption file was written")
    return files[0], None


# ---------------------------------------------------------------- parsing

TAG_RE = re.compile(r"<[^>]+>")
NOISE_RE = re.compile(r"\[(?:music|applause|laughter|music playing|音乐|掌声|笑声)\]|♪+", re.I)


def parse_cues(text: str):
    """VTT / SRT -> segments, removing YouTube's rolling duplicate lines."""
    segs, naive, recent = [], [], []
    for block in re.split(r"\r?\n\s*\r?\n", text.replace("﻿", "")):
        lines = block.splitlines()
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        start = parse_clock(lines[idx].split("-->")[0])
        if start is None:
            continue
        for raw in lines[idx + 1:]:
            line = html.unescape(TAG_RE.sub("", raw)).strip()
            if not line:
                continue
            naive.append((start, line))
            if segs and line == segs[-1][1] and start - segs[-1][0] < 60:
                continue  # rolling repeat: the previous line carried into the next cue
            if any(line == t and start - s < 20 for t, s in recent):
                continue  # repeated again a little later
            if segs and line.startswith(segs[-1][1]) and start - segs[-1][0] < 10:
                segs[-1] = (segs[-1][0], line)  # the same line, growing
            else:
                segs.append((start, line))
            recent = (recent + [(line, start)])[-4:]
    return segs, naive


def parse_json3(text: str):
    segs, naive = [], []
    for ev in json.loads(text).get("events") or []:
        parts = ev.get("segs")
        if not parts:
            continue
        line = "".join(p.get("utf8", "") for p in parts).replace("\n", " ").strip()
        if not line:
            continue
        start = (ev.get("tStartMs") or 0) / 1000
        naive.append((start, line))
        if segs and line == segs[-1][1]:
            continue
        segs.append((start, line))
    return segs, naive


PANEL_TS = re.compile(r"^\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?$")
PANEL_TS_TEXT = re.compile(r"^\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?\s+(.+)$")
# accessibility labels that YouTube's transcript panel adds when copied, e.g. "2 seconds", "1 分钟 5 秒钟"
PANEL_LABEL = re.compile(r"^(?:\d+\s*(?:hours?|minutes?|seconds?|小时|分钟|秒钟?|秒)[,，\s]*)+$", re.I)


def parse_panel(text: str):
    """Text copied from YouTube's "Show transcript" panel (timestamp lines + text lines)."""
    segs, cur_t, cur = [], None, ""
    for raw in text.replace("﻿", "").splitlines():
        line = raw.strip()
        if not line or PANEL_LABEL.match(line):
            continue
        m = PANEL_TS.match(line)
        m2 = None if m else PANEL_TS_TEXT.match(line)
        if m or m2:
            if cur:
                segs.append((cur_t, cur))
            cur_t = parse_clock((m or m2).group(1))
            cur = m2.group(2).strip() if m2 else ""
        elif cur_t is None:
            continue  # page text copied before the first timestamp ("Transcript", "Search in video", ...)
        else:
            cur = join_text(cur, line) if cur else line
    if cur:
        segs.append((cur_t, cur))
    return segs, segs


def looks_like_panel(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()][:200]
    stamps = sum(1 for l in lines if PANEL_TS.match(l) or PANEL_TS_TEXT.match(l))
    return stamps >= 3 and stamps >= len(lines) * 0.15


def parse_any(text: str, suffix: str):
    suffix = suffix.lower()
    if suffix in (".json3", ".json"):
        return parse_json3(text)
    if suffix in (".vtt", ".srt") or "-->" in text:
        return parse_cues(text)
    if looks_like_panel(text):
        return parse_panel(text)
    lines = [(None, l.strip()) for l in text.splitlines() if l.strip()]
    return lines, lines


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", NOISE_RE.sub("", text)).strip()


SENT_END = tuple("。！？!?.…」”\"")


def build_blocks(segs, block_seconds: int, chapters):
    starts = sorted(c.get("start_time") or 0 for c in chapters or [] if (c.get("start_time") or 0) > 0)
    blocks, cur, ci = [], None, 0
    for start, text in segs:
        text = clean_text(text)
        if not text:
            continue
        if start is None:
            blocks.append({"start": None, "text": text})
            continue
        new_chapter = ci < len(starts) and start >= starts[ci] - 0.5
        while ci < len(starts) and start >= starts[ci] - 0.5:
            ci += 1
        if cur is None or new_chapter or (
                start - cur["start"] >= block_seconds
                and (cur["text"].endswith(SENT_END) or start - cur["start"] >= block_seconds * 1.6)):
            cur = {"start": start, "end": start, "text": text}
            blocks.append(cur)
        else:
            cur["text"] = join_text(cur["text"], text)
            cur["end"] = start  # start time of the block's last line
    return blocks


# ---------------------------------------------------------------- output

def slugify(title: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip()
    return re.sub(r"\s+", "-", slug)[:60] or "video"


def notes_path(cfg: dict, vid: str) -> str:
    """ASCII-only file name (date + video id) so it never turns into garbled text."""
    d = Path(os.path.expanduser(cfg["notes_dir"]))
    d.mkdir(parents=True, exist_ok=True)
    return str(d / f"{date.today().isoformat()}_{re.sub(r'[^A-Za-z0-9_-]', '', vid) or 'video'}.md")


def finalize(vid: str, d: Path, segs, naive, raw_text: str, info, cfg: dict, source: dict) -> dict:
    info = info or {}
    chapters = info.get("chapters") or []
    blocks = build_blocks(segs, int(cfg["block_seconds"]), chapters)
    if not blocks:
        return {"status": "no_transcript", "message": "The transcript was empty after cleaning."}
    timed = [b for b in blocks if b["start"] is not None]
    speech_end = (timed[-1].get("end", timed[-1]["start"]) + 10) if timed else None
    duration = float(info.get("duration") or speech_end or 0)
    title = (source.get("title") or info.get("title") or vid).strip()
    url = info.get("webpage_url") or source.get("url") or ""
    link_base = f"https://youtu.be/{vid}?t=" if len(vid) == 11 and not vid.startswith("local-") else ""

    # transcript lines, with YouTube chapter headings
    lines, chs, ci = [], sorted(chapters, key=lambda c: c.get("start_time") or 0), 0
    for b in blocks:
        if b["start"] is None:
            lines.append((None, b["text"]))
            continue
        while ci < len(chs) and (chs[ci].get("start_time") or 0) <= b["start"] + 0.5:
            c = chs[ci]
            lines.append((b["start"], f"## {str(c.get('title', '')).strip()} [{fmt_time(c.get('start_time'))}]"))
            ci += 1
        lines.append((b["start"], f"[{fmt_time(b['start'])}] {b['text']}"))

    label = source["label"]
    header = [f"# {title}",
              f"<!-- id: {vid} | duration: {fmt_time(duration)} | source: {label} | fullwatch {VERSION} -->", ""]
    body = "\n".join(header + [l for _, l in lines]) + "\n"
    tfile = d / "transcript.md"
    tfile.write_text(body, encoding="utf-8")

    # split long videos into parts
    parts = []
    part_sec = int(cfg["part_minutes"]) * 60
    for old in d.glob("part-*.md"):
        old.unlink()
    if timed and duration > part_sec * 1.5:
        groups, bound = [[]], part_sec
        for start, text in lines:
            if start is not None and start >= bound and groups[-1]:
                groups.append([])
                while start >= bound:
                    bound += part_sec
            groups[-1].append((start, text))
        for i, g in enumerate(groups, 1):
            g_start = next((s for s, _ in g if s is not None), 0)
            nxt = groups[i][0][0] if i < len(groups) else duration
            pf = d / f"part-{i:02d}.md"
            rng = f"{fmt_time(g_start)}–{fmt_time(nxt)}"
            pf.write_text(f"# {title} — part {i}/{len(groups)} [{rng}]\n\n"
                          + "\n".join(t for _, t in g) + "\n", encoding="utf-8")
            parts.append({"file": str(pf), "range": rng, "lines": len(g)})

    # honesty checks: long silent gaps, captions ending early
    warnings = []
    for a, b in zip(timed, timed[1:]):
        last = a.get("end", a["start"])
        if b["start"] - last > 300:
            warnings.append(f"No speech between {fmt_time(last)} and {fmt_time(b['start'])} (music, silence, or missing captions).")
    incomplete = False
    if speech_end and duration and duration - speech_end > max(120, duration * 0.1):
        if source.get("kind") == "import":
            incomplete = True
            warnings.append(f"The transcript ends at {fmt_time(speech_end)} but the video is {fmt_time(duration)} long: "
                            "the user may not have copied all of it.")
        else:
            warnings.append(f"Speech ends at {fmt_time(speech_end)} but the video is {fmt_time(duration)} long.")
    if source.get("translated") is None and source.get("kind") == "auto":
        warnings.append("Could not confirm the caption track is the original language; it may be machine-translated.")
    if not timed:
        warnings.append("The transcript has no timestamps; the coverage check cannot run.")

    naive_text = "\n".join(f"[{fmt_time(s)}] {t}" if s is not None else t for s, t in naive)
    tokens = {"raw_file": est_tokens(raw_text), "naive": est_tokens(naive_text), "clean": est_tokens(body)}
    base = max(tokens["naive"], 1)
    tokens["saved_vs_naive"] = f"{max(0, round((1 - tokens['clean'] / base) * 100))}%"

    meta = {
        "id": vid, "url": url, "title": title,
        "channel": info.get("channel") or info.get("uploader") or "",
        "upload_date": info.get("upload_date") or "",
        "duration_s": round(duration, 1), "duration": fmt_time(duration),
        "speech_end_s": round(speech_end, 1) if speech_end else None,
        "chapters": [{"start": fmt_time(c.get("start_time")), "title": c.get("title")} for c in chs],
        "source": label, "source_detail": source,
        "transcript_file": str(tfile), "lines": len(lines), "parts": parts,
        "has_timestamps": bool(timed), "link_base": link_base,
        "tokens": tokens, "warnings": warnings, "transcript_may_be_incomplete": incomplete,
        "saved": datetime.now().isoformat(timespec="seconds"),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return result(meta, cfg)


def result(meta: dict, cfg: dict, cached: bool = False) -> dict:
    out = {"status": "ok", "cached": cached}
    for k in ("id", "title", "channel", "duration", "source", "chapters", "transcript_file",
              "lines", "parts", "link_base", "tokens", "warnings", "transcript_may_be_incomplete"):
        out[k] = meta.get(k)
    out["notes_path"] = notes_path(cfg, meta["id"])
    out["notes_template"] = str(SKILL_DIR / "references" / "notes-template.md")
    if meta.get("parts"):
        out["next"] = "Read EVERY part file in order, first line to last. Do not skip or sample."
    else:
        out["next"] = f"Read transcript_file completely ({meta['lines']} lines). Do not skip or sample."
    return out


# ---------------------------------------------------------------- commands

def ask_transcript(err: dict, vid: str, url: str) -> dict:
    """Automatic fetching failed (typical in the chat app): ask the user for the transcript instead."""
    if err.get("status") in ("needs_ytdlp", "network", "blocked", "error"):
        err = dict(err)
        err.update({
            "id": vid, "url": url, "ask_user_for_transcript": True,
            "guide": str(SKILL_DIR / "references" / "get-transcript.md"),
            "next": "Do NOT summarize from the title or description. Show the user the guide, wait for the "
                    f"transcript, save it to a .txt file, then run: import <file> --url \"{url}\"",
        })
    return err


def cmd_fetch(args, cfg) -> int:
    vid = video_id(args.url)
    if not vid:
        return emit({"status": "invalid_input", "message": "Not a YouTube link or video id."}, 2)
    d = vdir(vid)
    meta = load_meta(vid)
    if meta and not args.refresh and Path(meta["transcript_file"]).is_file():
        return emit(result(meta, cfg, cached=True))
    url = args.url if args.url.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
    info, err = get_info(url, d, args)
    if err:
        return emit(ask_transcript(err, vid, url), 2)
    if info.get("is_live"):
        return emit({"status": "unavailable", "message": "This is a live stream; try again after it ends."}, 2)
    prefs = ([args.lang] if args.lang else []) + list(cfg.get("caption_langs") or [])
    track = pick_track(info, prefs)
    if not track:
        duration = float(info.get("duration") or 0)
        return emit({"status": "no_captions", "id": vid, "title": info.get("title"),
                     "duration": fmt_time(duration),
                     "transcribe": transcribe_readiness(cfg, duration),
                     "hint": "Ask the user before transcribing locally, or let them import a transcript."}, 3)
    sub_file, err = download_subs(d, track, args)
    if err:
        return emit(ask_transcript(err, vid, url), 2)
    raw = sub_file.read_text(encoding="utf-8-sig", errors="replace")
    segs, naive = parse_any(raw, sub_file.suffix)
    label = f"captions: {track['kind']} ({track['key']})"
    res = finalize(vid, d, segs, naive, raw, info, cfg, {**track, "label": label, "url": url})
    return emit(res, 0 if res["status"] == "ok" else 2)


def cuda_count() -> int:
    try:
        import ctranslate2
        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def local_models(model_dir: Path) -> list:
    prefix = "models--Systran--faster-whisper-"
    return sorted(p.name[len(prefix):] for p in model_dir.glob(prefix + "*") if p.is_dir())


def load_stats() -> dict:
    p = HOME / "stats.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def plan_devices(cfg: dict, model_override, force_cpu: bool) -> list:
    w = cfg["whisper"]
    cpu_model = model_override or w.get("cpu_model") or w["model"]
    if force_cpu or w.get("device") == "cpu":
        return [("cpu", cpu_model)]
    plan = []
    if w.get("device") in ("auto", "cuda") and cuda_count() > 0:
        plan.append(("cuda", model_override or w["model"]))
    plan.append(("cpu", cpu_model))
    return plan


def transcribe_readiness(cfg: dict, duration: float) -> dict:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return {"ready": False, "reason": "faster-whisper is not installed",
                "hint": "python -m pip install -U faster-whisper"}
    model_dir = Path(os.path.expanduser(cfg["whisper"]["model_dir"]))
    have = local_models(model_dir)
    plan = [(dev, m) for dev, m in plan_devices(cfg, None, False) if m in have]
    if not plan:
        return {"ready": False, "reason": f"no matching model in {model_dir}", "models_found": have}
    dev, model = plan[0]
    rtf = load_stats().get(f"{dev}:{model}")
    return {"ready": True, "device": dev, "model": model,
            "estimate": fmt_time(duration * rtf) if rtf and duration else "unknown (first run will measure it)"}


def audio_duration(path: Path) -> float:
    try:
        import av
        with av.open(str(path)) as c:
            return (c.duration or 0) / 1_000_000
    except Exception:
        return 0.0


def whisper_run(audio: Path, model: str, device: str, cfg: dict, lang: str, allow_download: bool, total: float):
    from faster_whisper import WhisperModel
    w = cfg["whisper"]
    compute = "auto" if device == "cuda" else "int8"
    m = WhisperModel(model, device=device, compute_type=compute,
                     download_root=os.path.expanduser(w["model_dir"]),
                     local_files_only=not allow_download)
    prompt = w.get("initial_prompt") or (ZH_PROMPT if lang.startswith("zh") else None)
    segments, info = m.transcribe(str(audio), language=lang or None, initial_prompt=prompt,
                                  vad_filter=bool(w.get("vad", True)), beam_size=5)
    total = total or float(getattr(info, "duration", 0) or 0)
    out, last = [], time.time()
    for s in segments:
        out.append((float(s.start), s.text.strip()))
        if total and time.time() - last > 15:
            print(f"progress {min(100, s.end / total * 100):.0f}%  {fmt_time(s.end)} / {fmt_time(total)}",
                  file=sys.stderr, flush=True)
            last = time.time()
    return out, getattr(info, "language", "") or lang


def cmd_transcribe(args, cfg) -> int:
    w = cfg["whisper"]
    src = args.source
    local = Path(os.path.expanduser(src))
    is_file = local.is_file()
    vid = None if is_file else video_id(src)
    if not is_file and not vid:
        return emit({"status": "invalid_input", "message": "Give a YouTube link or an audio/video file path."}, 2)
    info = None
    if vid:
        d = vdir(vid)
        url = src if src.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
        info_path = d / "info.json"
        if info_path.is_file():
            info = json.loads(info_path.read_text(encoding="utf-8"))
        else:
            info, err = get_info(url, d, args)
            if err:
                return emit(err, 2)
        duration = float(info.get("duration") or 0)
    else:
        vid = "local-" + hashlib.sha1(str(local.resolve()).encode()).hexdigest()[:10]
        d = vdir(vid)
        url = ""
        duration = audio_duration(local)

    if args.estimate_only:
        return emit({"status": "ok", "id": vid, "duration": fmt_time(duration),
                     "transcribe": transcribe_readiness(cfg, duration)})
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return emit({"status": "needs_faster_whisper", "hint": "python -m pip install -U faster-whisper"}, 2)

    model_dir = Path(os.path.expanduser(w["model_dir"]))
    have = local_models(model_dir)
    plan = plan_devices(cfg, args.model, args.cpu)
    if not args.allow_download:
        plan = [(dev, m) for dev, m in plan if m in have]
    if not plan:
        return emit({"status": "model_missing", "model_dir": str(model_dir), "models_found": have,
                     "hint": "Download the model once in Buzz (Faster Whisper), set whisper.model in the "
                             "config to one you have, or rerun with --allow-download."}, 2)

    audio = local
    if not is_file:
        for old in d.glob("audio.*"):
            old.unlink()
        base = ytdlp_base(args)
        if base is None:
            return emit({"status": "needs_ytdlp", "hint": ytdlp_hint()}, 2)
        print("downloading audio ...", file=sys.stderr, flush=True)
        code, out, err = run(base + ["--load-info-json", str(d / "info.json"), "-f",
                                     "bestaudio[ext=m4a]/bestaudio/best", "-o", str(d / "audio.%(ext)s")],
                             timeout=1800)
        found = [f for f in d.glob("audio.*") if not f.name.endswith((".part", ".ytdl"))]
        if code != 0 or not found:
            return emit(failure(err or "audio download failed"), 2)
        audio = found[0]

    lang = args.lang or w.get("language") or ""
    errors, segs = [], None
    for dev, model in plan:
        print(f"transcribing on {dev} with {model} ...", file=sys.stderr, flush=True)
        t0 = time.time()
        try:
            segs, detected = whisper_run(audio, model, dev, cfg, lang, args.allow_download, duration)
        except Exception as exc:
            errors.append(f"{dev}/{model}: {str(exc)[:300]}")
            print(f"{dev} failed, trying the next option: {str(exc)[:200]}", file=sys.stderr, flush=True)
            continue
        elapsed = time.time() - t0
        break
    if segs is None:
        return emit({"status": "error", "message": "Local transcription failed.", "attempts": errors}, 2)
    if not is_file and not args.keep_audio:
        for f in d.glob("audio.*"):
            f.unlink()

    total = duration or (segs[-1][0] if segs else 0)
    if total:
        stats = load_stats()
        stats[f"{dev}:{model}"] = round(elapsed / total, 3)
        (HOME / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    raw = "\n".join(f"[{fmt_time(s)}] {t}" for s, t in segs)
    label = f"local whisper: {model} on {dev} ({detected or 'auto'})"
    res = finalize(vid, d, segs, segs, raw, info, cfg,
                   {"kind": "whisper", "label": label, "translated": False, "url": url,
                    "title": None if info else local.stem, "elapsed": fmt_time(elapsed)})
    if errors and res.get("status") == "ok":
        res["fallback_notes"] = errors
    return emit(res, 0 if res["status"] == "ok" else 2)


def cmd_import(args, cfg) -> int:
    p = Path(os.path.expanduser(args.file))
    if not p.is_file():
        return emit({"status": "invalid_input", "message": f"File not found: {p}"}, 2)
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    segs, naive = parse_any(raw, p.suffix)
    info, vid, url = None, None, args.url or ""
    if args.url:
        vid = video_id(args.url)
    if vid:
        d = vdir(vid)
        info, _ = get_info(args.url, d, args)  # metadata is optional here
    else:
        vid = "local-" + hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:10]
        d = vdir(vid)
    if args.duration and not (info or {}).get("duration"):
        secs = parse_clock(args.duration)
        if secs:
            info = {**(info or {}), "duration": secs}  # lets the script notice a partly copied transcript
    label = f"imported: {p.name}"
    res = finalize(vid, d, segs, naive, raw, info, cfg,
                   {"kind": "import", "label": label, "translated": False, "url": url,
                    "title": args.title or (None if info else p.stem)})
    return emit(res, 0 if res["status"] == "ok" else 2)


RANGE_RE = re.compile(r"\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—~至]\s*(\d{1,2}:\d{2}(?::\d{2})?|end|结束)\s*\]", re.I)


def cmd_coverage(args, cfg) -> int:
    meta = load_meta(args.id)
    if not meta:
        return emit({"status": "error", "message": f"No saved transcript for {args.id}. Run fetch first."}, 2)
    notes = Path(os.path.expanduser(args.notes))
    if not notes.is_file():
        return emit({"status": "error", "message": f"Notes not found: {notes}"}, 2)
    duration = float(meta.get("duration_s") or 0)
    must_reach = min(duration, float(meta.get("speech_end_s") or duration))
    ranges = []
    for line in notes.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.lstrip().startswith("#"):
            continue
        m = RANGE_RE.search(line)
        if m:
            a = parse_clock(m.group(1))
            b = duration if m.group(2).lower() in ("end", "结束") else parse_clock(m.group(2))
            ranges.append((a, b))
    tol = max(20.0, min(90.0, duration * 0.03))
    issues = []
    if not ranges:
        issues.append("No section headings like '### [00:00–12:30] Title' were found.")
    else:
        ranges.sort()
        if ranges[0][0] > tol:
            issues.append(f"Nothing covers 00:00–{fmt_time(ranges[0][0])}.")
        reach = ranges[0][1]
        for a, b in ranges[1:]:
            if a - reach > tol:
                issues.append(f"Gap: {fmt_time(reach)}–{fmt_time(a)} is not covered.")
            reach = max(reach, b)
        if reach < must_reach - tol:
            issues.append(f"Notes stop at {fmt_time(reach)}; speech continues to {fmt_time(must_reach)}.")
    return emit({"status": "ok" if not issues else "incomplete", "duration": meta.get("duration"),
                 "must_reach": fmt_time(must_reach),
                 "sections": [f"{fmt_time(a)}–{fmt_time(b)}" for a, b in ranges], "issues": issues},
                0 if not issues else 1)


QUOTE_RE = re.compile(r"「([^」]{2,500})」")


def norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def cmd_quotes(args, cfg) -> int:
    meta = load_meta(args.id)
    if not meta:
        return emit({"status": "error", "message": f"No saved transcript for {args.id}. Run fetch first."}, 2)
    notes = Path(os.path.expanduser(args.notes))
    if not notes.is_file():
        return emit({"status": "error", "message": f"Notes not found: {notes}"}, 2)
    lines = Path(meta["transcript_file"]).read_text(encoding="utf-8").splitlines()
    body = " ".join(re.sub(r"^\[\d[\d:]*\]\s*", "", l) for l in lines if l and not l.startswith(("#", "<!--")))
    target = norm(body)
    matcher = difflib.SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(target)
    checked = []
    for m in QUOTE_RE.finditer(notes.read_text(encoding="utf-8", errors="replace")):
        quote = m.group(1).strip()
        nq = norm(quote)
        if len(nq) < 4:
            continue
        if nq in target:
            checked.append({"quote": quote[:120], "result": "found"})
            continue
        matcher.set_seq1(nq)
        best = matcher.find_longest_match(0, len(nq), 0, len(target))
        ratio = best.size / len(nq)
        checked.append({"quote": quote[:120], "result": "close" if ratio >= 0.8 else "not_found",
                        "match": f"{round(ratio * 100)}%"})
    bad = [c for c in checked if c["result"] == "not_found"]
    return emit({"status": "ok" if not bad else "unverified", "checked": len(checked),
                 "not_found": bad, "close": [c for c in checked if c["result"] == "close"],
                 "hint": "Quotes must be verbatim transcript text in the original language. Fix or delete every not_found quote."
                 if bad else ""}, 0 if not bad else 1)


def cmd_find(args, cfg) -> int:
    terms = [t.lower() for t in args.query.split() if t.strip()]
    hits = []

    def score(title: str, text: str):
        s, snip, low = 0, "", text.lower()
        for t in terms:
            if t in title.lower():
                s += 3
            i = low.find(t)
            if i >= 0:
                s += 1
                snip = snip or text[max(0, i - 60):i + 100].replace("\n", " ")
        return s, snip

    for mp in (HOME / "videos").glob("*/meta.json"):
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            text = "\n".join(l for l in Path(meta["transcript_file"]).read_text(encoding="utf-8").splitlines()
                             if not l.startswith("<!--"))
        except Exception:
            continue
        s, snip = score(meta.get("title", ""), text)
        if s:
            hits.append({"score": s, "type": "transcript", "id": meta["id"], "title": meta.get("title"),
                         "file": meta["transcript_file"], "snippet": snip})
    nd = Path(os.path.expanduser(cfg["notes_dir"]))
    for nf in nd.glob("*.md") if nd.is_dir() else []:
        text = nf.read_text(encoding="utf-8", errors="replace")
        s, snip = score(nf.stem, text)
        if s:
            hits.append({"score": s, "type": "notes", "title": nf.stem, "file": str(nf), "snippet": snip})
    hits.sort(key=lambda h: -h["score"])
    return emit({"status": "ok", "query": args.query, "results": hits[:10]})


def cmd_doctor(args, cfg) -> int:
    created = False
    if args.init and not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fresh = json.loads(json.dumps(DEFAULTS))
        fresh["whisper"]["model_dir"] = cfg["whisper"]["model_dir"]
        CONFIG_PATH.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        created = True
        cfg = load_config()
    yt = shutil.which("yt-dlp")
    yt_version = run([yt, "--version"], 30)[1].strip() if yt else None
    if not yt:
        try:
            import yt_dlp
            yt_version = getattr(yt_dlp.version, "__version__", "module")
        except Exception:
            pass
    fw_version = None
    try:
        import faster_whisper
        fw_version = getattr(faster_whisper, "__version__", None) or "installed"
    except Exception:
        pass
    model_dir = Path(os.path.expanduser(cfg["whisper"]["model_dir"]))
    have = local_models(model_dir)
    gpus = cuda_count() if fw_version else 0
    hints = []
    if not yt_version:
        hints.append("Install yt-dlp (required): " + ytdlp_hint())
    if not shutil.which("deno"):
        hints.append("Optional: YouTube sometimes needs a JavaScript runtime for yt-dlp: "
                     + ("winget install --id DenoLand.Deno --exact" if IS_WINDOWS else "install Deno (deno.com)"))
    if fw_version and av_hint():
        hints.append(av_hint())
    if fw_version and IS_WINDOWS and gpus and not _DLL_DIRS_ADDED:
        hints.append("GPU found but no CUDA DLL folder. Set whisper.buzz_dir to your Buzz install (e.g. F:\\Buzz) "
                     "to reuse its CUDA files, or: python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")
    if not fw_version:
        hints.append("Optional (videos without captions): python -m pip install -U faster-whisper \"av<16\"")
    elif not have:
        hints.append(f"Optional: no faster-whisper models in {model_dir}. Download one in Buzz, or set whisper.model_dir.")
    elif gpus and cfg["whisper"]["model"] not in have:
        hints.append(f"whisper.model '{cfg['whisper']['model']}' is not downloaded; you have {have}.")
    return emit({
        "status": "ok" if yt_version else "needs_ytdlp",
        "version": VERSION,
        "config_file": str(CONFIG_PATH), "config_created": created,
        "first_run": created or not CONFIG_PATH.exists(),
        "python": platform.python_version(),
        "yt_dlp": yt_version, "deno": bool(shutil.which("deno")),
        "faster_whisper": fw_version, "cuda_gpus": gpus, "cuda_dll_dirs": _DLL_DIRS_ADDED,
        "model_dir": str(model_dir), "models": have,
        "settings": {"notes_dir": cfg["notes_dir"], "output_language": cfg.get("output_language"),
                     "lens": cfg.get("lens"), "whisper_model": cfg["whisper"]["model"],
                     "cpu_model": cfg["whisper"].get("cpu_model"), "whisper_language": cfg["whisper"].get("language")},
        "ready": {"captions": bool(yt_version), "local_transcription": bool(fw_version and have)},
        "hints": hints,
    }, 0 if yt_version else 2)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(prog="fullwatch", description="Read the full transcript of a YouTube video.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def net(p):
        p.add_argument("--cookies-from-browser", metavar="BROWSER")
        p.add_argument("--cookies", metavar="FILE")

    p = sub.add_parser("doctor")
    p.add_argument("--init", action="store_true", help="create the config file if missing")
    p = sub.add_parser("fetch")
    p.add_argument("url")
    p.add_argument("--lang", help="preferred caption language, e.g. zh-Hans or en")
    p.add_argument("--refresh", action="store_true")
    net(p)
    p = sub.add_parser("transcribe")
    p.add_argument("source", help="YouTube link or local audio/video file")
    p.add_argument("--model")
    p.add_argument("--lang", help="spoken language, e.g. zh or en")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--keep-audio", action="store_true")
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--allow-download", action="store_true", help="allow downloading a missing model")
    net(p)
    p = sub.add_parser("import")
    p.add_argument("file")
    p.add_argument("--url")
    p.add_argument("--title")
    p.add_argument("--duration", help="video length, e.g. 55:43 or 1:02:10 (from the video page)")
    net(p)
    p = sub.add_parser("coverage")
    p.add_argument("notes")
    p.add_argument("id")
    p = sub.add_parser("quotes")
    p.add_argument("notes")
    p.add_argument("id")
    p = sub.add_parser("find")
    p.add_argument("query")

    args = ap.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    add_cuda_dll_dirs(cfg)  # before ctranslate2 is imported anywhere
    return {"doctor": cmd_doctor, "fetch": cmd_fetch, "transcribe": cmd_transcribe, "import": cmd_import,
            "coverage": cmd_coverage, "quotes": cmd_quotes, "find": cmd_find}[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
