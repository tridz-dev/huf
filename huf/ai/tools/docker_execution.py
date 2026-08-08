import json
import subprocess
import shlex
import frappe

DESTRUCTIVE_ACTIONS = {"stop_container", "restart_container", "remove_container"}
COMPOSE_DESTRUCTIVE_ACTIONS = {"compose_down"}
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300


def _require_value(kwargs, name):
    value = kwargs.get(name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return value


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _compose_args(action, kwargs):
    compose_file = _require_value(kwargs, "compose_file")
    project_dir = kwargs.get("project_dir")
    project_name = kwargs.get("project_name")
    args = ["compose"]
    if project_dir:
        args.extend(["--project-directory", project_dir])
    args.extend(["-f", compose_file])
    if project_name:
        args.extend(["-p", project_name])

    if action == "compose_up":
        args.append("up")
        if kwargs.get("detach", True):
            args.append("-d")
        if kwargs.get("build"):
            args.append("--build")
        if kwargs.get("wait"):
            args.append("--wait")
        if kwargs.get("remove_orphans"):
            args.append("--remove-orphans")
        args.extend(_split_csv(kwargs.get("services")))
    elif action == "compose_ps":
        args.extend(["ps", "--all"])
    elif action == "compose_logs":
        args.append("logs")
        if kwargs.get("tail") is not None:
            args.extend(["--tail", str(kwargs["tail"])])
        args.extend(_split_csv(kwargs.get("services")))
    elif action == "compose_config":
        args.append("config")
    elif action == "compose_down":
        args.append("down")
        if kwargs.get("remove_orphans"):
            args.append("--remove-orphans")
        if kwargs.get("remove_volumes"):
            args.append("--volumes")
    else:
        raise ValueError(f"Unknown action: {action}")
    return args

def _build_docker_base_cmd(kwargs):
    cmd = ["docker"]
    connection_string = kwargs.get("connection_string")
    context_name = kwargs.get("context_name")
    
    if context_name:
        cmd.extend(["--context", context_name])
    elif connection_string:
        cmd.extend(["-H", connection_string])
        if kwargs.get("tls_verify"):
            cmd.append("--tlsverify")
        for option, field in (
            ("--tlscacert", "tls_ca_cert"),
            ("--tlscert", "tls_cert"),
            ("--tlskey", "tls_key"),
        ):
            if kwargs.get(field):
                cmd.extend([option, kwargs[field]])
            
    return cmd

def _run_subprocess(cmd, timeout=DEFAULT_TIMEOUT_SECONDS):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=timeout
        )
        return {
            "success": True,
            "output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr or e.stdout or str(e),
            "output": e.stdout,
            "stderr": e.stderr,
            "exit_code": e.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "success": False,
            "error": f"Docker command timed out after {timeout} seconds",
            "output": e.stdout or "",
            "stderr": e.stderr or "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "Docker CLI is not installed or not on PATH. Install docker-cli in the Huf runtime or use ssh_connection for a remote Docker host.",
            "output": "",
            "stderr": "",
        }

def _run_via_ssh_connection(ssh_connection, cmd_str, timeout=DEFAULT_TIMEOUT_SECONDS):
    from huf.ai.tools.ssh_execution import _connect_transport, _run_exec_over_transport
    
    doc = frappe.get_doc("SSH Connection", ssh_connection)
    limits = {
        "connection_timeout_seconds": 10,
        "execution_timeout_seconds": min(timeout, MAX_TIMEOUT_SECONDS),
        "stdout_max_bytes": 1048576,
        "stderr_max_bytes": 1048576,
        "combined_output_max_bytes": 2097152,
    }
    transport, fingerprint, host_key_type = _connect_transport(doc, limits)
    try:
        res = _run_exec_over_transport(transport, cmd_str, limits, fingerprint, host_key_type)
        if res.exit_code == 0:
            return {"success": True, "output": res.stdout, "stderr": res.stderr, "exit_code": 0}
        else:
            return {
                "success": False,
                "error": res.stderr or f"Exit code {res.exit_code}",
                "output": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.exit_code,
            }
    finally:
        transport.close()

def handle_action(**kwargs):
    action = kwargs.get("action")
    ssh_connection = kwargs.get("ssh_connection")
    if (action in DESTRUCTIVE_ACTIONS or action in COMPOSE_DESTRUCTIVE_ACTIONS) and not kwargs.get("confirm_destructive"):
        return {
            "success": False,
            "error": f"{action} requires confirm_destructive=true",
        }

    try:
        args = []
        if action in {"compose_up", "compose_ps", "compose_logs", "compose_config", "compose_down"}:
            args = _compose_args(action, kwargs)
        elif action == "list_containers":
            args = ["ps", "-a", "--format", "{{json .}}"]
        elif action == "list_images":
            args = ["images", "--format", "{{json .}}"]
        elif action == "inspect_container":
            args = ["inspect", _require_value(kwargs, "container")]
        elif action == "logs":
            args = ["logs", _require_value(kwargs, "container")]
            if kwargs.get("tail") is not None:
                args.extend(["--tail", str(kwargs["tail"])])
        elif action == "stop_container":
            args = ["stop", _require_value(kwargs, "container")]
        elif action == "start_container":
            args = ["start", _require_value(kwargs, "container")]
        elif action == "restart_container":
            args = ["restart", _require_value(kwargs, "container")]
        elif action == "remove_container":
            args = ["rm", "-f", _require_value(kwargs, "container")]
        elif action == "pull_image":
            args = ["pull", _require_value(kwargs, "image")]
        elif action == "run_container":
            args = ["run", "-d"]
            if kwargs.get("name"):
                args.extend(["--name", kwargs["name"]])
            if kwargs.get("ports"):
                for port in _split_csv(kwargs["ports"]):
                    args.extend(["-p", port])
            if kwargs.get("environment"):
                for env in _split_csv(kwargs["environment"]):
                    args.extend(["-e", env])
            if kwargs.get("volumes"):
                for volume in _split_csv(kwargs["volumes"]):
                    args.extend(["-v", volume])
            if kwargs.get("network"):
                args.extend(["--network", kwargs["network"]])
            if kwargs.get("workdir"):
                args.extend(["--workdir", kwargs["workdir"]])
            if kwargs.get("user"):
                args.extend(["--user", kwargs["user"]])
            if kwargs.get("memory"):
                args.extend(["--memory", kwargs["memory"]])
            if kwargs.get("cpus"):
                args.extend(["--cpus", str(kwargs["cpus"])])
            if kwargs.get("auto_remove"):
                args.append("--rm")
            args.append(_require_value(kwargs, "image"))
            if kwargs.get("command"):
                args.extend(shlex.split(kwargs["command"]))
        elif action == "exec_container":
            args = ["exec"]
            if kwargs.get("workdir"):
                args.extend(["--workdir", kwargs["workdir"]])
            args.extend([_require_value(kwargs, "container")])
            args.extend(shlex.split(_require_value(kwargs, "command")))
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc)}

    try:
        timeout = min(
            max(int(kwargs.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)), 1),
            MAX_TIMEOUT_SECONDS,
        )
    except (TypeError, ValueError):
        return {"success": False, "error": "timeout_seconds must be an integer"}

    if action not in {
        "compose_up", "compose_ps", "compose_logs", "compose_config", "compose_down",
        "list_containers", "list_images", "inspect_container", "logs",
        "stop_container", "start_container", "restart_container",
        "remove_container", "pull_image", "run_container", "exec_container",
    }:
        return {"success": False, "error": f"Unknown action: {action}"}

    if ssh_connection:
        cmd_str = "docker " + shlex.join(args)
        result = _run_via_ssh_connection(ssh_connection, cmd_str, timeout=timeout)
    else:
        cmd = _build_docker_base_cmd(kwargs) + args
        result = _run_subprocess(cmd, timeout=timeout)

    if result.get("success") and result.get("stderr"):
        result["output"] = (result.get("output") or "") + result["stderr"]

    # Attempt to parse json for list commands
    if result["success"] and action in ("list_containers", "list_images"):
        lines = result["output"].strip().split("\n")
        parsed = []
        for line in lines:
            if line.strip():
                try:
                    parsed.append(json.loads(line))
                except Exception:
                    parsed.append(line)
        result["output"] = parsed
        
    if result["success"] and action == "inspect_container":
        try:
            result["output"] = json.loads(result["output"])
        except Exception:
            pass
            
    return result
