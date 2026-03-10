import json
import frappe


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
			{
				"id": c.short_id, 
				"name": c.name, 
				"status": c.status, 
				"image": str(c.image.tags[0]) if c.image.tags else str(c.image.id[:12])
			}
			for c in containers
		]
		return json.dumps({
			"success": True, 
			"count": len(result), 
			"results": result
		})
	except Exception as e:
		frappe.log_error(f"Docker Error (List Containers): {str(e)}", "Docker Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_run_container(**kwargs):
	"""Run a new Docker container."""
	try:
		image = kwargs.get("image")
		if not image:
			return json.dumps({"success": False, "error": "image is required"})

		client = _client()
		run_kwargs = {"image": image, "detach": True}
		if "command" in kwargs:
			run_kwargs["command"] = kwargs["command"]
		if "name" in kwargs:
			run_kwargs["name"] = kwargs["name"]

		container = client.containers.run(**run_kwargs)
		return json.dumps({
			"success": True, 
			"results": {
				"id": container.short_id, 
				"name": container.name, 
				"status": container.status
			}
		})
	except Exception as e:
		frappe.log_error(f"Docker Error (Run Container): {str(e)}", "Docker Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_container_logs(**kwargs):
	"""Get logs from a Docker container."""
	try:
		container_id = kwargs.get("container_id")
		if not container_id:
			return json.dumps({"success": False, "error": "container_id is required"})

		client = _client()
		container = client.containers.get(container_id)
		tail = int(kwargs.get("tail", 100))
		logs = container.logs(tail=tail).decode("utf-8", errors="replace")
		return json.dumps({
			"success": True, 
			"results": {
				"container_id": container_id, 
				"logs": logs[:10000]
			}
		})
	except Exception as e:
		frappe.log_error(f"Docker Error (Logs): {str(e)}", "Docker Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_list_images(**kwargs):
	"""List Docker images."""
	try:
		client = _client()
		images = client.images.list()
		result = [
			{
				"id": img.short_id, 
				"tags": img.tags, 
				"size_mb": round(img.attrs.get("Size", 0) / 1e6, 1)
			}
			for img in images
		]
		return json.dumps({
			"success": True, 
			"count": len(result), 
			"results": result
		})
	except Exception as e:
		frappe.log_error(f"Docker Error (List Images): {str(e)}", "Docker Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_pull_image(**kwargs):
	"""Pull a Docker image from a registry."""
	try:
		image_name = kwargs.get("image_name")
		if not image_name:
			return json.dumps({"success": False, "error": "image_name is required"})

		client = _client()
		image = client.images.pull(image_name)
		return json.dumps({
			"success": True, 
			"results": {
				"id": image.short_id, 
				"tags": image.tags
			}
		})
	except Exception as e:
		frappe.log_error(f"Docker Error (Pull Image): {str(e)}", "Docker Tool")
		return json.dumps({"success": False, "error": str(e)})
