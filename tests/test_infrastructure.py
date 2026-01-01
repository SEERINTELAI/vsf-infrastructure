"""Infrastructure validation tests for VSF."""
from typing import Any
import pytest

class TestHugePages:
    @pytest.mark.infrastructure
    def test_hugepages_configured(self, check_hugepages: dict[str, Any]) -> None:
        if check_hugepages["total_pages"] == 0:
            pytest.skip("HugePages not configured (expected in CI)")

    @pytest.mark.infrastructure
    def test_hugepages_sufficient(self, check_hugepages: dict[str, Any]) -> None:
        if check_hugepages["total_pages"] == 0:
            pytest.skip("HugePages not configured")
        assert check_hugepages["total_memory_gb"] >= 560

class TestPackages:
    @pytest.mark.infrastructure
    def test_packages_check_runs(self, check_packages: dict[str, Any]) -> None:
        assert isinstance(check_packages, dict)

class TestResourceCapacity:
    @pytest.mark.infrastructure
    def test_cpu_cores(self, run_command, skip_unless_host) -> None:
        skip_unless_host()
        result = run_command(["nproc"], capture_output=True, check=False)
        if result.returncode == 0:
            cores = int(result.stdout.strip())
            assert cores >= 140, f"Need 140+ cores, have {cores}"
