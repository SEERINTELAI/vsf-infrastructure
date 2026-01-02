#!/bin/bash
#
# pre-flight-gpu.sh - Comprehensive GPU compatibility check for F10.2 Task 111
#
# Run this BEFORE deploying NVIDIA GPU Operator to validate GPU readiness.
# Exit code 0 = all checks pass, non-zero = failures detected
#
# Usage:
#   ./pre-flight-gpu.sh [node]           # Check specific node (default: all GPU workers)
#   ./pre-flight-gpu.sh --all            # Check all GPU worker nodes
#   ./pre-flight-gpu.sh --report         # Generate detailed report
#
# Requirements:
#   - SSH access to GPU worker nodes
#   - sudo privileges on target nodes
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="${SCRIPT_DIR}/gpu-preflight-report-$(date +%Y%m%d-%H%M%S).md"

# GPU worker nodes (adjust as needed)
GPU_WORKERS=(vsf-gpu-1 vsf-gpu-2 vsf-gpu-3 vsf-gpu-4 vsf-gpu-5 vsf-gpu-6 vsf-gpu-7 vsf-gpu-8)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS_COUNT++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL_COUNT++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN_COUNT++))
}

log_info() {
    echo -e "[INFO] $1"
}

# Check if we can SSH to node
check_ssh() {
    local node=$1
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$node" "echo ok" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Run command on node, return output
run_on_node() {
    local node=$1
    shift
    ssh -o ConnectTimeout=10 "$node" "$@" 2>/dev/null
}

# Check 1: nvidia-smi basic availability
check_nvidia_smi() {
    local node=$1
    log_info "[$node] Checking nvidia-smi..."
    
    if run_on_node "$node" "nvidia-smi --query-gpu=name,driver_version --format=csv,noheader" &>/dev/null; then
        local gpu_info
        gpu_info=$(run_on_node "$node" "nvidia-smi --query-gpu=name,driver_version --format=csv,noheader")
        log_pass "[$node] nvidia-smi works: $gpu_info"
        return 0
    else
        log_fail "[$node] nvidia-smi failed or not available"
        return 1
    fi
}

# Check 2: Kernel module compatibility
check_kernel_modules() {
    local node=$1
    log_info "[$node] Checking kernel modules..."
    
    local kernel_version
    kernel_version=$(run_on_node "$node" "uname -r")
    
    local nvidia_vermagic
    nvidia_vermagic=$(run_on_node "$node" "modinfo nvidia 2>/dev/null | grep vermagic | head -1" || echo "")
    
    if [[ -z "$nvidia_vermagic" ]]; then
        log_fail "[$node] nvidia kernel module not found"
        return 1
    fi
    
    if echo "$nvidia_vermagic" | grep -q "$kernel_version"; then
        log_pass "[$node] nvidia module matches kernel $kernel_version"
        return 0
    else
        log_warn "[$node] nvidia module vermagic may not match kernel $kernel_version"
        log_info "[$node] Module info: $nvidia_vermagic"
        return 0  # Warning, not failure
    fi
}

# Check 3: CUDA runtime availability
check_cuda() {
    local node=$1
    log_info "[$node] Checking CUDA runtime..."
    
    local cuda_version
    cuda_version=$(run_on_node "$node" "nvcc --version 2>/dev/null | grep 'release' | awk '{print \$6}'" || echo "")
    
    if [[ -n "$cuda_version" ]]; then
        log_pass "[$node] CUDA available: $cuda_version"
        return 0
    else
        log_warn "[$node] CUDA toolkit not installed (may be installed by GPU Operator)"
        return 0  # Warning, not failure - GPU Operator can install
    fi
}

# Check 4: Container runtime GPU support
check_container_runtime() {
    local node=$1
    log_info "[$node] Checking container runtime GPU support..."
    
    # Check if nvidia-container-toolkit is installed
    if run_on_node "$node" "which nvidia-container-cli" &>/dev/null; then
        log_pass "[$node] nvidia-container-toolkit installed"
    else
        log_warn "[$node] nvidia-container-toolkit not found (GPU Operator will install)"
    fi
    
    # Check containerd nvidia runtime config
    local containerd_config
    containerd_config=$(run_on_node "$node" "cat /etc/containerd/config.toml 2>/dev/null | grep -c nvidia" || echo "0")
    
    if [[ "$containerd_config" -gt 0 ]]; then
        log_pass "[$node] containerd has nvidia runtime configured"
        return 0
    else
        log_warn "[$node] containerd nvidia runtime not configured (GPU Operator will configure)"
        return 0
    fi
}

# Check 5: IOMMU groups for passthrough
check_iommu() {
    local node=$1
    log_info "[$node] Checking IOMMU configuration..."
    
    # Check if IOMMU is enabled
    local iommu_groups
    iommu_groups=$(run_on_node "$node" "ls /sys/kernel/iommu_groups/ 2>/dev/null | wc -l" || echo "0")
    
    if [[ "$iommu_groups" -gt 0 ]]; then
        log_pass "[$node] IOMMU enabled ($iommu_groups groups)"
    else
        log_warn "[$node] No IOMMU groups found - may not affect GPU Operator"
    fi
    
    # Check GPU IOMMU isolation
    local gpu_class="0x0302"  # 3D controller
    local gpu_in_iommu
    gpu_in_iommu=$(run_on_node "$node" "
        for d in /sys/kernel/iommu_groups/*/devices/*; do
            if [[ -f \"\$d/class\" ]] && grep -q '$gpu_class' \"\$d/class\" 2>/dev/null; then
                echo 'found'
                break
            fi
        done
    " || echo "")
    
    if [[ "$gpu_in_iommu" == "found" ]]; then
        log_pass "[$node] GPU found in IOMMU group"
    else
        log_info "[$node] GPU IOMMU group check inconclusive"
    fi
    
    return 0
}

# Check 6: GPU device enumeration
check_gpu_devices() {
    local node=$1
    log_info "[$node] Checking GPU device enumeration..."
    
    local gpu_count
    gpu_count=$(run_on_node "$node" "nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null | head -1" || echo "0")
    
    if [[ "$gpu_count" -gt 0 ]]; then
        log_pass "[$node] $gpu_count GPU(s) detected"
        
        # Get detailed GPU info
        local gpu_details
        gpu_details=$(run_on_node "$node" "nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader" || echo "")
        log_info "[$node] GPU details: $gpu_details"
        return 0
    else
        log_fail "[$node] No GPUs detected"
        return 1
    fi
}

# Check 7: GPU memory and utilization baseline
check_gpu_baseline() {
    local node=$1
    log_info "[$node] Capturing GPU baseline metrics..."
    
    local baseline
    baseline=$(run_on_node "$node" "nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader" || echo "")
    
    if [[ -n "$baseline" ]]; then
        log_pass "[$node] Baseline captured: $baseline"
        return 0
    else
        log_warn "[$node] Could not capture GPU baseline"
        return 0
    fi
}

# Check 8: VFIO driver binding (for passthrough scenarios)
check_vfio() {
    local node=$1
    log_info "[$node] Checking VFIO configuration..."
    
    # Check if vfio-pci module is available
    if run_on_node "$node" "modinfo vfio-pci" &>/dev/null; then
        log_pass "[$node] vfio-pci module available"
    else
        log_warn "[$node] vfio-pci module not available"
    fi
    
    # Check GPU driver binding
    local gpu_drivers
    gpu_drivers=$(run_on_node "$node" "
        for d in /sys/bus/pci/devices/*/driver; do
            if [[ -L \"\$d\" ]]; then
                dev=\$(dirname \$d)
                if [[ -f \"\$dev/class\" ]] && grep -q '0x0302' \"\$dev/class\" 2>/dev/null; then
                    readlink \$d | xargs basename
                fi
            fi
        done | sort -u
    " || echo "unknown")
    
    log_info "[$node] GPU driver bindings: $gpu_drivers"
    return 0
}

# Run all checks on a node
check_node() {
    local node=$1
    echo ""
    echo "========================================"
    echo "Checking node: $node"
    echo "========================================"
    
    if ! check_ssh "$node"; then
        log_fail "[$node] Cannot SSH to node"
        return 1
    fi
    
    check_nvidia_smi "$node" || true
    check_kernel_modules "$node" || true
    check_cuda "$node" || true
    check_container_runtime "$node" || true
    check_iommu "$node" || true
    check_gpu_devices "$node" || true
    check_gpu_baseline "$node" || true
    check_vfio "$node" || true
}

# Generate report
generate_report() {
    cat > "$REPORT_FILE" << EOF
# GPU Pre-Flight Report

**Generated**: $(date -Iseconds)
**Nodes Checked**: ${#GPU_WORKERS[@]}

## Summary

| Metric | Count |
|--------|-------|
| Passed | $PASS_COUNT |
| Failed | $FAIL_COUNT |
| Warnings | $WARN_COUNT |

## Recommendation

EOF

    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo "✅ **PROCEED**: All critical checks passed." >> "$REPORT_FILE"
    else
        echo "❌ **DO NOT PROCEED**: $FAIL_COUNT critical failures detected." >> "$REPORT_FILE"
    fi
    
    if [[ $WARN_COUNT -gt 0 ]]; then
        echo "" >> "$REPORT_FILE"
        echo "⚠️ **$WARN_COUNT warnings** - review before proceeding." >> "$REPORT_FILE"
    fi
    
    echo "" >> "$REPORT_FILE"
    echo "## Next Steps" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "If all checks pass:" >> "$REPORT_FILE"
    echo "1. Review warnings and address if critical" >> "$REPORT_FILE"
    echo "2. Proceed with GPU Operator deployment (Task 111)" >> "$REPORT_FILE"
    echo "3. Run post-deployment validation" >> "$REPORT_FILE"
    
    log_info "Report saved to: $REPORT_FILE"
}

# Main
main() {
    local target="${1:-all}"
    
    echo "============================================"
    echo "GPU Pre-Flight Check for F10.2 Task 111"
    echo "============================================"
    echo ""
    
    if [[ "$target" == "--all" || "$target" == "all" ]]; then
        for node in "${GPU_WORKERS[@]}"; do
            check_node "$node"
        done
    elif [[ "$target" == "--report" ]]; then
        for node in "${GPU_WORKERS[@]}"; do
            check_node "$node"
        done
        generate_report
    else
        check_node "$target"
    fi
    
    echo ""
    echo "============================================"
    echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed, $WARN_COUNT warnings"
    echo "============================================"
    
    if [[ $FAIL_COUNT -gt 0 ]]; then
        echo ""
        log_fail "Pre-flight checks FAILED - do not proceed with GPU Operator deployment"
        exit 1
    else
        echo ""
        log_pass "Pre-flight checks PASSED - safe to proceed with GPU Operator deployment"
        exit 0
    fi
}

main "$@"
