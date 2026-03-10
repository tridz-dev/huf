import json
import re
import frappe
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


def handle_get_video_data(**kwargs):
	"""Get metadata of a YouTube video (title, author, etc.)."""
	try:
		from pytube import YouTube
	except ImportError:
		try:
			from pytubefix import YouTube
		except ImportError:
			return json.dumps({"success": False, "error": "pytube or pytubefix required. Install with: pip install pytubefix"})

	try:
		url = kwargs.get("url")
		if not url:
			return json.dumps({"success": False, "error": "URL is required"})

		yt = YouTube(url)
		return json.dumps({
			"success": True,
			"results": {
				"title": yt.title,
				"author": yt.author,
				"length_seconds": yt.length,
				"views": yt.views,
				"publish_date": str(yt.publish_date) if yt.publish_date else None,
				"description": (yt.description or "")[:1000],
			}
		})
	except Exception as e:
		frappe.log_error(f"YouTube Get Video Data Error: {str(e)}", "YouTube Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_captions(**kwargs):
	"""Get captions/transcript of a YouTube video."""
	try:
		from youtube_transcript_api import YouTubeTranscriptApi
	except ImportError:
		return json.dumps({
			"success": False,
			"error": "youtube-transcript-api required. Install with: pip install youtube-transcript-api"
		})

	try:
		url = kwargs.get("url")
		if not url:
			return json.dumps({"success": False, "error": "URL is required"})

		video_id = _extract_video_id(url)
		ytt_api = YouTubeTranscriptApi()
		transcript = ytt_api.fetch(video_id)
		
		# youtube-transcript-api returns FetchedTranscript with .snippets list of Snippet objects
		if hasattr(transcript, "snippets"):
			text = " ".join(snippet.text for snippet in transcript.snippets)
		else:
			# Fallback for older API versions that return list of dicts
			text = " ".join(item.get("text", "") for item in transcript)
		return json.dumps({
			"success": True, 
			"results": {
				"video_id": video_id,
				"transcript": text[:10000]
			}
		})
	except Exception as e:
		frappe.log_error(f"YouTube Get Captions Error: {str(e)}", "YouTube Tool")
		return json.dumps({"success": False, "error": str(e)})
