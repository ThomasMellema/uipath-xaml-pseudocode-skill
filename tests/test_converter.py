from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "uipath_xaml_to_pseudocode.py"
FIXTURES = ROOT / "tests" / "fixtures"
PSEUDOCODE_FIXTURES = FIXTURES / "pseudocode"
SNAPSHOT_FIXTURES = [
    "large_workflow",
    "ui_browser_workflow",
    "excel_datatable_workflow",
    "queue_assets_workflow",
    "mail_api_files_workflow",
    "ref_main_state_machine",
    "ref_get_transaction_data",
    "ref_process_set_status",
]


def convert_fixture(name: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(FIXTURES / name)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def convert_fixture_relative(name: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        out_path = Path(temp) / f"{Path(name).stem}.uipath.py"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--file",
                str(Path("tests") / "fixtures" / name),
                "--out",
                str(out_path),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return out_path.read_text(encoding="utf-8")


class ConverterTests(unittest.TestCase):
    def test_simple_workflow_preserves_core_logic(self) -> None:
        output = convert_fixture("simple.xaml")

        self.assertIn("invoice: 'x:String' = None", output)
        self.assertIn('invoice = expr(\'row("InvoiceNumber").ToString.Trim\')', output)
        self.assertIn("if expr('invoice <> String.Empty'):", output)
        self.assertIn("log(level='Info', message=expr('invoice'))", output)
        self.assertIn('raise_uipath_exception(expr(\'New BusinessRuleException("Missing invoice")\'))', output)

    def test_activitybuilder_implementation_is_not_dropped(self) -> None:
        output = convert_fixture("activitybuilder.xaml")

        self.assertIn("# Sequence: Builder Main", output)
        self.assertIn('name = expr(\'"Alice"\')', output)
        self.assertNotIn("activity_builder()", output)

    def test_switch_renders_cases_and_default(self) -> None:
        output = convert_fixture("switch.xaml")

        self.assertIn("switch expr('status'):", output)
        self.assertIn("case 'OK':", output)
        self.assertIn("case 'ERR':", output)
        self.assertIn("default:", output)
        self.assertNotIn("string()", output)

    def test_redaction_masks_literals_but_keeps_config_keys(self) -> None:
        output = convert_fixture("redaction.xaml")

        self.assertIn("display_name='Enter password'", output)
        self.assertIn("text=redacted()", output)
        self.assertIn("aaname='<redacted>'", output)
        self.assertIn("id='password'", output)
        self.assertIn("token=<redacted>", output)
        self.assertIn('expr(\'Config("Password").ToString\')', output)
        self.assertNotIn("hunter2", output)
        self.assertNotIn("abc123456789", output)
        self.assertNotIn("Acme Corp secret portal", output)

    def test_retry_scope_has_action_and_condition_blocks(self) -> None:
        output = convert_fixture("retry_scope.xaml")

        self.assertIn("retry_scope(number_of_retries=expr('3'), retry_interval=expr('00:00:05')):", output)
        self.assertIn("action:", output)
        self.assertIn("condition:", output)

    def test_saved_pseudocode_snapshots_match_converter_output(self) -> None:
        for name in SNAPSHOT_FIXTURES:
            with self.subTest(name=name):
                output = convert_fixture_relative(f"{name}.xaml")
                expected = (PSEUDOCODE_FIXTURES / f"{name}.uipath.py").read_text(encoding="utf-8")
                self.assertEqual(expected, output)

    def test_broad_activity_coverage_has_expected_signals(self) -> None:
        ui_output = (PSEUDOCODE_FIXTURES / "ui_browser_workflow.uipath.py").read_text(encoding="utf-8")
        excel_output = (PSEUDOCODE_FIXTURES / "excel_datatable_workflow.uipath.py").read_text(encoding="utf-8")
        queue_output = (PSEUDOCODE_FIXTURES / "queue_assets_workflow.uipath.py").read_text(encoding="utf-8")
        mail_output = (PSEUDOCODE_FIXTURES / "mail_api_files_workflow.uipath.py").read_text(encoding="utf-8")

        self.assertIn("use_application_browser(", ui_output)
        self.assertIn("check_app_state(display_name='Check dashboard'):", ui_output)
        self.assertIn("text=redacted()", ui_output)
        self.assertNotIn("plain-password-123", ui_output)
        self.assertIn("use_excel_file(", excel_output)
        self.assertIn("filter_data_table(", excel_output)
        self.assertIn("cell=expr", excel_output)
        self.assertIn("get_transaction_item(", queue_output)
        self.assertIn("set_transaction_status(", queue_output)
        self.assertIn("custom_vendor_activity(", queue_output)
        self.assertIn('credential_name=expr(\'Config("CredentialName").ToString\')', queue_output)
        self.assertIn("password=redacted()", queue_output)
        self.assertIn("get_outlook_mail_messages(", mail_output)
        self.assertIn("http_client(", mail_output)
        self.assertIn("token=<redacted>", mail_output)
        self.assertNotIn("abc123456789", mail_output)

    def test_reframework_coverage_has_expected_signals(self) -> None:
        main_output = (PSEUDOCODE_FIXTURES / "ref_main_state_machine.uipath.py").read_text(encoding="utf-8")
        get_data_output = (PSEUDOCODE_FIXTURES / "ref_get_transaction_data.uipath.py").read_text(encoding="utf-8")
        process_output = (PSEUDOCODE_FIXTURES / "ref_process_set_status.uipath.py").read_text(encoding="utf-8")

        self.assertIn("state_machine(initial='Init'):", main_output)
        self.assertIn("state 'Get Transaction Data':", main_output)
        self.assertIn("'SetTransactionStatus.xaml'", main_output)
        self.assertIn("io_RetryNumber=inout('RetryNumber')", main_output)
        self.assertIn('queue_name=expr(\'Config("OrchestratorQueueName").ToString\')', get_data_output)
        self.assertIn("out_TransactionID = expr('out_TransactionItem.Reference')", get_data_output)
        self.assertIn('invoiceNumber = expr(\'in_TransactionItem.SpecificContent("InvoiceNumber").ToString\')', process_output)
        self.assertIn("set_transaction_status(", process_output)
        self.assertIn("rethrow()", process_output)

    def test_parse_error_returns_fallback(self) -> None:
        output = convert_fixture("invalid.xaml")

        self.assertIn("# Parse error:", output)
        self.assertIn("# Fallback: raw XAML was not rendered.", output)

    def test_directory_conversion_writes_matching_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp) / "pseudo"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--dir", str(FIXTURES), "--out", str(out_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            for fixture in FIXTURES.glob("*.xaml"):
                self.assertTrue((out_dir / f"{fixture.stem}.uipath.py").exists())


if __name__ == "__main__":
    unittest.main()
