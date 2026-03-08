import json
import re

from huf.ai.tools.credentials import require_credential
import requests


def _extract_video_id(url):
	patterns = [
		r"(?:v=|/v/|youtu\.be/)([^&?#]+)",
		r"(?:embed/)([^&?#]+)",
	]
	for p in patterns:
		m = re.search(p, url)
		if m:
			return m.group(1)
	return url


def _get_api_key():
	return require_credential("youtube", "api_key")


def handle_get_video_data(**kwargs):
	"""Get metadata of a YouTube video (title, author, etc.)."""
	try:
		from pytube import YouTube
	except ImportError:
		try:
			from pytubefix import YouTube
		except ImportError:
			return json.dumps({"error": "pytube or pytubefix required. Install with: pip install pytubefix"})

	try:
		yt = YouTube(kwargs["url"])
		return json.dumps({
			"title": yt.title,
			"author": yt.author,
			"length_seconds": yt.length,
			"views": yt.views,
			"publish_date": str(yt.publish_date) if yt.publish_date else None,
			"description": (yt.description or "")[:1000],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_captions(**kwargs):
	"""Get captions/transcript of a YouTube video."""
	try:
		from youtube_transcript_api import YouTubeTranscriptApi
	except ImportError:
		return json.dumps({
			"error": "youtube-transcript-api required. Install with: pip install youtube-transcript-api"
		})

	try:
		video_id = _extract_video_id(kwargs["url"])
		ytt_api = YouTubeTranscriptApi()
		transcript = ytt_api.fetch(video_id)
		text = " ".join(snippet.text for snippet in transcript.snippets)
		return json.dumps({"video_id": video_id, "transcript": text[:10000]})
	except Exception as e:
		return json.dumps({"error": str(e)})
