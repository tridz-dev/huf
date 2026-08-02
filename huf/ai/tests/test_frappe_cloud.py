import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools.frappe_cloud import (
    handle_fc_add_ssh_key,
    handle_fc_add_webhook,
    handle_fc_archive_bench,
    handle_fc_create_bench,
    handle_fc_create_site,
    handle_fc_delete_webhook,
    handle_fc_generate_bench_ssh_certificate,
    handle_fc_list_benches,
    handle_fc_site_options,
)


def _mock_account():
    account = MagicMock()
    account.server_url = "https://frappecloud.com"
    account.api_key = "test_key"
    account.get_password.return_value = "test_secret"
    return account


class TestFrappeCloudTools(unittest.TestCase):
    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_list_benches(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": [{"name": "bench-1", "title": "Bench 1", "extra": "raw"}]}'
        mock_response.json.return_value = {"message": [{"name": "bench-1", "title": "Bench 1", "extra": "raw"}]}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_list_benches()
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"], [{"name": "bench-1", "title": "Bench 1"}])
        mock_request.assert_called_once()
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.bench.all"))

        result = handle_fc_list_benches(full=True)
        data = json.loads(result)
        self.assertEqual(data["results"][0]["extra"], "raw")

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_site(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"name": "site-1"}}'
        mock_response.json.return_value = {"message": {"name": "site-1"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_create_site(
            bench="bench-1",
            site_name="site-1",
            version="Version 16",
            domain="frappe.cloud",
            plan="USD 5",
        )
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"]["name"], "site-1")
        payload = mock_request.call_args.kwargs["json"]
        self.assertEqual(payload["site"]["name"], "site-1")
        self.assertEqual(payload["site"]["group"], "bench-1")
        self.assertEqual(payload["site"]["plan"], "USD 5")

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_site_requires_version_domain_plan(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        result = handle_fc_create_site(bench="bench-1", site_name="site-1")
        data = json.loads(result)
        self.assertFalse(data["success"])
        self.assertIn("version, domain, and plan are required", data["error"])
        mock_request.assert_not_called()

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_bench(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": "bench-1"}'
        mock_response.json.return_value = {"message": "bench-1"}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_create_bench(
            title="test-bench",
            version="Version 16",
            cluster="UAE",
            apps=[{"name": "frappe", "source": "SRC-frappe-237"}],
        )
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"], "bench-1")
        payload = mock_request.call_args.kwargs["json"]
        self.assertEqual(payload["bench"]["title"], "test-bench")
        self.assertEqual(payload["bench"]["apps"][0]["name"], "frappe")

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_bench_requires_version_cluster_apps(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        result = handle_fc_create_bench(title="test-bench")
        data = json.loads(result)
        self.assertFalse(data["success"])
        self.assertIn("version and cluster are required", data["error"])
        mock_request.assert_not_called()

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_archive_bench(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = "{}"
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_archive_bench(bench="bench-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.bench.archive"))

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_site_options_uses_current_endpoint(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"versions": [], "domain": "frappe.cloud"}}'
        mock_response.json.return_value = {"message": {"versions": [], "domain": "frappe.cloud"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_site_options(bench="bench-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"]["domain"], "frappe.cloud")
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.site.options_for_new"))
        self.assertEqual(mock_request.call_args.kwargs["json"], {"for_bench": "bench-1"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_add_webhook(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = "{}"
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_add_webhook(endpoint="https://example.com/webhook", secret="secret", events=["Site Status Update"])
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.webhook.add"))
        self.assertEqual(mock_request.call_args.kwargs["json"]["events"], ["Site Status Update"])

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_delete_webhook(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = "{}"
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_delete_webhook(name="webhook-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.client.delete"))
        self.assertEqual(mock_request.call_args.kwargs["json"], {"doctype": "Press Webhook", "name": "webhook-1"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_add_ssh_key(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = "{}"
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_add_ssh_key(key="ssh-ed25519 AAAATEST huf")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.account.add_key"))
        self.assertEqual(mock_request.call_args.kwargs["json"], {"key": "ssh-ed25519 AAAATEST huf"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_generate_bench_ssh_certificate(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"name": "cert-1", "valid_until": "soon", "private": "raw"}}'
        mock_response.json.return_value = {"message": {"name": "cert-1", "valid_until": "soon", "private": "raw"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_generate_bench_ssh_certificate(bench="bench-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"], {"name": "cert-1", "valid_until": "soon"})
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.bench.generate_certificate"))
        self.assertEqual(mock_request.call_args.kwargs["json"], {"name": "bench-1"})


    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_bench_on_server(self, mock_request, mock_get_account):
        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": "bench-on-server"}'
        mock_response.json.return_value = {"message": "bench-on-server"}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_create_bench(
            title="test-bench",
            version="Version 16",
            cluster="UAE",
            apps=[{"name": "frappe", "source": "SRC-frappe-237"}],
            server="u32-singapore-do.frappe.cloud",
        )
        data = json.loads(result)
        self.assertTrue(data["success"])
        payload = mock_request.call_args.kwargs["json"]
        self.assertEqual(payload["bench"]["server"], "u32-singapore-do.frappe.cloud")

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_list_servers(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_list_servers

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": [{"name": "srv-1", "title": "Server 1", "status": "Active"}]}'
        mock_response.json.return_value = {"message": [{"name": "srv-1", "title": "Server 1", "status": "Active"}]}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_list_servers()
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"][0]["name"], "srv-1")
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.server.all"))

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_get_server(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_get_server

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"name": "srv-1", "title": "Server 1", "status": "Active"}}'
        mock_response.json.return_value = {"message": {"name": "srv-1", "title": "Server 1", "status": "Active"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_get_server(server="srv-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["results"]["title"], "Server 1")
        self.assertEqual(mock_request.call_args.kwargs["json"], {"name": "srv-1"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_unified_server(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_create_server

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"server": "srv-1", "job": "job-1"}}'
        mock_response.json.return_value = {"message": {"server": "srv-1", "job": "job-1"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_create_server(title="My Server", cluster="singapore", app_plan="plan-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        payload = mock_request.call_args.kwargs["json"]["server"]
        self.assertEqual(payload["title"], "My Server")
        self.assertEqual(payload["app_plan"], "plan-1")
        self.assertNotIn("db_plan", payload)
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.server.new_unified"))

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_create_server_with_db_plan(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_create_server

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": {"server": "srv-1", "job": "job-1"}}'
        mock_response.json.return_value = {"message": {"server": "srv-1", "job": "job-1"}}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_create_server(title="My Server", cluster="singapore", app_plan="plan-1", db_plan="db-plan-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.server.new"))
        self.assertEqual(mock_request.call_args.kwargs["json"]["server"]["db_plan"], "db-plan-1")

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_list_server_benches(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_list_server_benches

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": [{"name": "rg-1", "title": "RG 1"}]}'
        mock_response.json.return_value = {"message": [{"name": "rg-1", "title": "RG 1"}]}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_list_server_benches(server="srv-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.server.groups"))
        self.assertEqual(mock_request.call_args.kwargs["json"], {"name": "srv-1"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_reboot_server(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_reboot_server

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": "rebooted"}'
        mock_response.json.return_value = {"message": "rebooted"}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_reboot_server(server="srv-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.server.reboot"))

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_change_server_plan(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_change_server_plan

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{}'
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_change_server_plan(server="srv-1", plan="plan-pro")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.kwargs["json"], {"name": "srv-1", "plan": "plan-pro"})

    @patch("huf.ai.tools.frappe_cloud._get_fc_account")
    @patch("huf.ai.tools.frappe_cloud.httpx.request")
    def test_handle_fc_list_bench_jobs(self, mock_request, mock_get_account):
        from huf.ai.tools.frappe_cloud import handle_fc_list_bench_jobs

        mock_get_account.return_value = _mock_account()
        mock_response = MagicMock()
        mock_response.text = '{"message": [{"name": "job-1", "job_type": "Deploy"}]}'
        mock_response.json.return_value = {"message": [{"name": "job-1", "job_type": "Deploy"}]}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = handle_fc_list_bench_jobs(bench="rg-1")
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(mock_request.call_args.args[:2], ("POST", "https://frappecloud.com/api/method/press.api.bench.jobs"))
        self.assertEqual(mock_request.call_args.kwargs["json"]["filters"], {"bench": "rg-1"})
