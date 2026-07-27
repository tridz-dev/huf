import sys
from unittest.mock import MagicMock
sys.modules['frappe'] = MagicMock()

import unittest
from unittest.mock import patch

from huf.ai.tools.docker_execution import handle_action

class TestDockerExecution(unittest.TestCase):
    
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
            ports="80:80, 443:443"
        )
        
        mock_run.assert_called_once()
        expected_cmd = ["docker", "run", "-d", "--name", "web", "-p", "80:80", "-p", "443:443", "nginx"]
        self.assertEqual(mock_run.call_args[0][0], expected_cmd)

    @patch("huf.ai.tools.docker_execution._run_via_ssh_connection")
    def test_ssh_connection(self, mock_ssh):
        mock_ssh.return_value = {"success": True, "output": "some output"}
        
        res = handle_action(
            action="stop_container",
            container="web",
            ssh_connection="Test Server"
        )
        
        mock_ssh.assert_called_once_with("Test Server", "docker stop web")
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

if __name__ == "__main__":
    unittest.main()
