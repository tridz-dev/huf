import json
import subprocess
import os
import shlex
import frappe

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
            
    return cmd

def _run_subprocess(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "output": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": e.stderr}

def _run_via_ssh_connection(ssh_connection, cmd_str):
    from huf.ai.tools.ssh_execution import _connect_transport, _run_exec_over_transport
    
    doc = frappe.get_doc("SSH Connection", ssh_connection)
    limits = {
        "connection_timeout_seconds": 10,
        "execution_timeout_seconds": 60,
        "stdout_max_bytes": 1048576,
        "stderr_max_bytes": 1048576,
        "combined_output_max_bytes": 2097152,
    }
    transport, fingerprint, host_key_type = _connect_transport(doc, limits)
    try:
        res = _run_exec_over_transport(transport, cmd_str, limits, fingerprint, host_key_type)
        if res.exit_code == 0:
            return {"success": True, "output": res.stdout}
        else:
            return {"success": False, "error": res.stderr or f"Exit code {res.exit_code}"}
    finally:
        transport.close()

def handle_action(**kwargs):
    action = kwargs.get("action")
    ssh_connection = kwargs.get("ssh_connection")
    
    args = []
    if action == "list_containers":
        args = ["ps", "-a", "--format", "{{json .}}"]
    elif action == "list_images":
        args = ["images", "--format", "{{json .}}"]
    elif action == "inspect_container":
        container = kwargs.get("container")
        args = ["inspect", container]
    elif action == "logs":
        container = kwargs.get("container")
        args = ["logs", container]
        if kwargs.get("tail"):
            args.extend(["--tail", str(kwargs.get("tail"))])
    elif action == "stop_container":
        container = kwargs.get("container")
        args = ["stop", container]
    elif action == "start_container":
        container = kwargs.get("container")
        args = ["start", container]
    elif action == "restart_container":
        container = kwargs.get("container")
        args = ["restart", container]
    elif action == "remove_container":
        container = kwargs.get("container")
        args = ["rm", "-f", container]
    elif action == "pull_image":
        image = kwargs.get("image")
        args = ["pull", image]
    elif action == "run_container":
        image = kwargs.get("image")
        args = ["run", "-d"]
        if kwargs.get("name"):
            args.extend(["--name", kwargs.get("name")])
        if kwargs.get("ports"):
            for p in kwargs.get("ports").split(","):
                args.extend(["-p", p.strip()])
        args.append(image)
    elif action == "exec_container":
        container = kwargs.get("container")
        cmd_arg = kwargs.get("command")
        args = ["exec", container] + shlex.split(cmd_arg)
    else:
        return {"success": False, "error": f"Unknown action: {action}"}
        
    if ssh_connection:
        cmd_str = "docker " + shlex.join(args)
        result = _run_via_ssh_connection(ssh_connection, cmd_str)
    else:
        cmd = _build_docker_base_cmd(kwargs) + args
        result = _run_subprocess(cmd)
        
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
