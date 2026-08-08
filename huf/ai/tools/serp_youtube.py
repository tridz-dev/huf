"""SerpApi YouTube search tool plus a YouTube transcript tool (no SerpApi key)."""

import json

import frappe

from huf.ai.tools import serp_common
from huf.ai.tools.credentials import update_last_error
from huf.ai.tools.serp_common import SerpValidationError, _cfg, _safe_float

logger = frappe.logger("huf")

SERVICE_NAME = serp_common.SERVICE_NAME


def _default_gl():
	return _cfg("default_gl", "in")


def _default_hl():
	return _cfg("default_hl", "en")


def _video_id_from_link(link: str) -> str:
	link = str(link or "")
	if "watch?v=" in link:
		return link.split("watch?v=", 1)[1].split("&", 1)[0]
	if "youtu.be/" in link:
		return link.split("youtu.be/", 1)[1].split("?", 1)[0]
	if "/shorts/" in link:
		return link.split("/shorts/", 1)[1].split("?", 1)[0]
	return ""


def _normalize_video(video: dict) -> dict:
	channel = video.get("channel") or {}
	thumb = video.get("thumbnail") or {}
	link = str(video.get("link", ""))
	return {
		"title": str(video.get("title", "")),
		"link": link,
		"video_id": _video_id_from_link(link),
		"channel": str(channel.get("name", "")),
		"channel_link": str(channel.get("link", "")),
		"published_date": str(video.get("published_date", "")),
		"views": _safe_float(video.get("views")),
		"length": str(video.get("length", "")),
		"description": str(video.get("description", "")),
		"thumbnail": str(thumb.get("static", "") if isinstance(thumb, dict) else thumb),
	}


def handle_serp_youtube_search(**kwargs) -> str:
	"""Search YouTube videos via the SerpApi YouTube engine."""
	try:
		search_query = kwargs.get("search_query")
		if not search_query or not str(search_query).strip():
			raise SerpValidationError("search_query is required.")

		params = {
			"engine": "youtube",
			"search_query": str(search_query).strip(),
			"gl": kwargs.get("gl") or _default_gl(),
			"hl": kwargs.get("hl") or _default_hl(),
		}
		if kwargs.get("sp"):
			params["sp"] = kwargs.get("sp")

		results = serp_common._search(params)
		videos = [_normalize_video(v) for v in (results.get("video_results") or [])]

		return json.dumps({"success": True, "videos": videos, "search_query": params["search_query"]})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (YouTube Search): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def _extract_video_id(video: str) -> str:
	"""Accept a raw video id or any common YouTube URL and return the id."""
	v = str(video or "").strip()
	if not v:
		return ""
	if "watch?v=" in v:
		return v.split("watch?v=", 1)[1].split("&", 1)[0]
	if "youtu.be/" in v:
		return v.split("youtu.be/", 1)[1].split("?", 1)[0]
	if "/shorts/" in v:
		return v.split("/shorts/", 1)[1].split("?", 1)[0]
	if "/embed/" in v:
		return v.split("/embed/", 1)[1].split("?", 1)[0]
	return v  # already an id


def _coerce_langs(languages) -> list:
	if languages in (None, ""):
		return ["en"]
	if isinstance(languages, str):
		parts = [p.strip() for p in languages.split(",") if p.strip()]
	elif isinstance(languages, list | tuple):
		parts = [str(p).strip() for p in languages if str(p).strip()]
	else:
		parts = []
	return parts or ["en"]


def handle_youtube_transcript(**kwargs) -> str:
	"""Fetch the transcript/captions for a YouTube video.

	Uses the youtube-transcript-api package (no SerpApi credit consumed).
	`video` may be a video id or any YouTube URL (watch, youtu.be, shorts, embed).
	`languages` may be a list or comma string (e.g. "en,hi"); the first available
	match is returned.
	"""
	try:
		# Imported lazily so the module loads even if the package is absent.
		try:
			from youtube_transcript_api import YouTubeTranscriptApi
		except ImportError:
			raise SerpValidationError(
				"youtube-transcript-api is not installed. Run: bench pip install youtube-transcript-api"
			)

		video_id = _extract_video_id(kwargs.get("video"))
		if not video_id:
			raise SerpValidationError("A video id or YouTube URL is required.")

		langs = _coerce_langs(kwargs.get("languages"))

		try:
			fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)
		except Exception as exc:
			# TranscriptsDisabled / NoTranscriptFound / VideoUnavailable, etc.
			raise SerpValidationError(f"Could not fetch transcript for '{video_id}': {exc!s}")

		segments = [
			{
				"text": str(row.get("text", "")),
				"start": float(row.get("start", 0) or 0),
				"duration": float(row.get("duration", 0) or 0),
			}
			for row in fetched.to_raw_data()
		]

		return json.dumps(
			{
				"success": True,
				"video_id": video_id,
				"language": getattr(fetched, "language_code", "") or langs[0],
				"segments": segments,
				"full_text": " ".join(s["text"] for s in segments).strip(),
				"segment_count": len(segments),
			}
		)
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"YouTube Transcript Error: {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})
