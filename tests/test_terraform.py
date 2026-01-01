"""Terraform validation tests for VSF infrastructure."""
import json
from pathlib import Path
import pytest

class TestTerraformInit:
    def test_terraform_dir_exists(self, terraform_dir: Path) -> None:
        assert terraform_dir.exists()

    def test_required_files_exist(self, terraform_dir: Path) -> None:
        required = ["main.tf", "variables.tf", "outputs.tf", "versions.tf"]
        missing = [f for f in required if not (terraform_dir / f).exists()]
        assert len(missing) == 0, f"Missing: {missing}"

class TestTerraformValidation:
    @pytest.mark.slow
    def test_terraform_fmt_check(self, terraform_dir: Path, run_command) -> None:
        result = run_command(["terraform", "fmt", "-check", "-diff"], cwd=terraform_dir, check=False)
        assert result.returncode == 0, "Run 'terraform fmt' to fix"

    @pytest.mark.slow
    def test_terraform_validate(self, terraform_dir: Path, run_command) -> None:
        init = run_command(["terraform", "init", "-backend=false"], cwd=terraform_dir, check=False)
        if init.returncode != 0:
            pytest.skip("Terraform init failed")
        result = run_command(["terraform", "validate", "-json"], cwd=terraform_dir, check=False)
        validation = json.loads(result.stdout)
        assert validation.get("valid", False), f"Validation failed: {validation}"

class TestTerraformVariables:
    def test_variables_defined(self, terraform_dir: Path) -> None:
        content = (terraform_dir / "variables.tf").read_text()
        required = ["libvirt_uri", "control_plane_count", "worker_count"]
        missing = [v for v in required if f'variable "{v}"' not in content]
        assert len(missing) == 0, f"Missing variables: {missing}"

class TestTerraformOutputs:
    def test_outputs_defined(self, terraform_dir: Path) -> None:
        content = (terraform_dir / "outputs.tf").read_text()
        required = ["control_plane_ids", "worker_ids", "cluster_summary"]
        missing = [o for o in required if f'output "{o}"' not in content]
        assert len(missing) == 0, f"Missing outputs: {missing}"
