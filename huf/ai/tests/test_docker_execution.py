import sys
from unittest.mock import MagicMock
sys.modules['frappe'] = MagicMock()

import unittest
from unittest.mock import patch

from huf.ai.tools.docker_execution import handle_action

class TestDockerExecution(unittest.TestCase):

    def test_destructive_actions_require_confirmation(self):
        res = handle_action(action="remove_container", container="web")
        self.assertFalse(res["success"])
        self.assertIn("confirm_destructive", res["error"])

    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_required_fields_and_timeout_are_bounded(self, mock_run):
        self.assertFalse(handle_action(action="exec_container", container="web")["success"])
        mock_run.return_value = {"success": True, "output": "", "stderr": ""}
        handle_action(action="list_containers", timeout_seconds=9999)
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 300)

    @patch("huf.ai.tools.docker_execution.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_docker_cli_is_actionable(self, mock_run):
        result = handle_action(action="list_containers")
        self.assertFalse(result["success"])
        self.assertIn("Docker CLI is not installed", result["error"])

    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_compose_up_builds_bounded_command(self, mock_run):
        mock_run.return_value = {"success": True, "output": "ok\n", "stderr": ""}
        result = handle_action(
            action="compose_up",
            compose_file="/srv/app/compose.yml",
            project_dir="/srv/app",
            project_name="demo",
            services="web,worker",
            build=True,
            wait=True,
        )
        self.assertTrue(result["success"])
        self.assertEqual(
            mock_run.call_args[0][0],
            [
                "docker", "compose", "--project-directory", "/srv/app", "-f", "/srv/app/compose.yml",
                "-p", "demo", "up", "-d", "--build", "--wait", "web", "worker",
            ],
        )

    def test_compose_down_requires_confirmation(self):
        result = handle_action(action="compose_down", compose_file="/srv/app/compose.yml")
        self.assertFalse(result["success"])
        self.assertIn("confirm_destructive", result["error"])
    
    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_list_containers_local(self, mock_run):
        mock_run.return_value = {"success": True, "output": '{"ID":"123","Names":"test_container"}\n'}
        
        res = handle_action(action="list_containers")
        
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], ["docker", "ps", "-a", "--format", "{{json .}}"])
        
        self.assertTrue(res["success"])
        self.assertEqual(len(res["output"]), 1)
        self.assertEqual(res["output"][0]["ID"], "123")
        
    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_run_container(self, mock_run):
        mock_run.return_value = {"success": True, "output": "hash1234"}
        
        res = handle_action(
            action="run_container", 
            image="nginx", 
            name="web", 
            ports="80:80, 443:443",
            environment="APP_ENV=test,PORT=80",
            volumes="/tmp/data:/data:ro",
            network="bridge",
            command="nginx -g 'daemon off;'",
        )
        
        mock_run.assert_called_once()
        expected_cmd = ["docker", "run", "-d", "--name", "web", "-p", "80:80", "-p", "443:443", "-e", "APP_ENV=test", "-e", "PORT=80", "-v", "/tmp/data:/data:ro", "--network", "bridge", "nginx", "nginx", "-g", "daemon off;"]
        self.assertEqual(mock_run.call_args[0][0], expected_cmd)

    @patch("huf.ai.tools.docker_execution._run_via_ssh_connection")
    def test_ssh_connection(self, mock_ssh):
        mock_ssh.return_value = {"success": True, "output": "some output"}
        
        res = handle_action(
            action="stop_container",
            container="web",
            ssh_connection="Test Server",
            confirm_destructive=True,
        )
        
        mock_ssh.assert_called_once_with("Test Server", "docker stop web", timeout=60)
        self.assertTrue(res["success"])

    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_context_and_tls(self, mock_run):
        mock_run.return_value = {"success": True, "output": ""}
        
        handle_action(
            action="inspect_container",
            container="app",
            connection_string="tcp://10.0.0.1:2376",
            tls_verify=True
        )
        
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0][:4], ["docker", "-H", "tcp://10.0.0.1:2376", "--tlsverify"])
        self.assertEqual(mock_run.call_args[0][0][-2:], ["inspect", "app"])

    @patch("huf.ai.tools.docker_execution._run_subprocess")
    def test_tls_certificate_flags(self, mock_run):
        mock_run.return_value = {"success": True, "output": "", "stderr": ""}
        handle_action(
            action="list_containers",
            connection_string="tcp://docker.example:2376",
            tls_verify=True,
            tls_ca_cert="/certs/ca.pem",
            tls_cert="/certs/cert.pem",
            tls_key="/certs/key.pem",
        )
        command = mock_run.call_args[0][0]
        self.assertEqual(
            command[:10],
            ["docker", "-H", "tcp://docker.example:2376", "--tlsverify", "--tlscacert", "/certs/ca.pem", "--tlscert", "/certs/cert.pem", "--tlskey", "/certs/key.pem"],
        )

if __name__ == "__main__":
    unittest.main()
