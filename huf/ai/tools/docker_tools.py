import json


def _client():
	try:
		import docker
	except ImportError:
		raise ImportError("docker is required. Install with: pip install docker")
	return docker.from_env()


def handle_list_containers(**kwargs):
	"""List Docker containers."""
	try:
		client = _client()
		all_containers = kwargs.get("all", False)
		containers = client.containers.list(all=all_containers)
		result = [
			{"id": c.short_id, "name": c.name, "status": c.status, "image": str(c.image.tags[0]) if c.image.tags else str(c.image.id[:12])}
			for c in containers
		]
		return json.dumps({"count": len(result), "containers": result})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_run_container(**kwargs):
	"""Run a new Docker container."""
	try:
		client = _client()
		run_kwargs = {"image": kwargs["image"], "detach": True}
		if "command" in kwargs:
			run_kwargs["command"] = kwargs["command"]
		if "name" in kwargs:
			run_kwargs["name"] = kwargs["name"]

		container = client.containers.run(**run_kwargs)
		return json.dumps({"id": container.short_id, "name": container.name, "status": container.status})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_container_logs(**kwargs):
	"""Get logs from a Docker container."""
	try:
		client = _client()
		container = client.containers.get(kwargs["container_id"])
		tail = int(kwargs.get("tail", 100))
		logs = container.logs(tail=tail).decode("utf-8", errors="replace")
		return json.dumps({"container_id": kwargs["container_id"], "logs": logs[:10000]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_images(**kwargs):
	"""List Docker images."""
	try:
		client = _client()
		images = client.images.list()
		result = [
			{"id": img.short_id, "tags": img.tags, "size_mb": round(img.attrs.get("Size", 0) / 1e6, 1)}
			for img in images
		]
		return json.dumps({"count": len(result), "images": result})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_pull_image(**kwargs):
	"""Pull a Docker image from a registry."""
	try:
		client = _client()
		image = client.images.pull(kwargs["image_name"])
		return json.dumps({"id": image.short_id, "tags": image.tags})
	except Exception as e:
		return json.dumps({"error": str(e)})
