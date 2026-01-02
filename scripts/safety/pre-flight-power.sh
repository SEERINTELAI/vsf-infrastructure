#!/bin/bash
#
# pre-flight-power.sh - Multi-source RAPL validation for F10.2 Task 115
#
# Run this BEFORE deploying Kepler to validate power monitoring capability.
# Tests RAPL access in VMs and on hypervisor for Scaphandre fallback.
#
# Usage:
#   ./pre-flight-power.sh [node]           # Check specific node
#   ./pre-flight-power.sh --workers        # Check all worker nodes
#   ./pre-flight-power.sh --hypervisor     # Check hypervisor (Bizon1)
#   ./pre-flight-power.sh --all            # Check everything
#
# Requirements:
#   - SSH access to worker nodes and hypervisor
#   - sudo privileges for RAPL access
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="${SCRIPT_DIR}/power-preflight-report-$(date +%Y%m%d-%H%M%S).md"

# Worker nodes
WORKERS=(vsf-worker-1 vsf-worker-2 vsf-worker-3 vsf-worker-4 vsf-worker-5
         vsf-worker-6 vsf-worker-7 vsf-worker-8 vsf-worker-9 vsf-worker-10)
GPU_WORKERS=(vsf-gpu-1 vsf-gpu-2 vsf-gpu-3 vsf-gpu-4 vsf-gpu-5 vsf-gpu-6 vsf-gpu-7 vsf-gpu-8)
HYPERVISOR="bizon1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
RAPL_AVAILABLE_COUNT=0
RAPL_UNAVAILABLE_COUNT=0

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL_COUNT++)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARN_COUNT++)); }
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

check_ssh() {
    local node=$1
    ssh -o ConnectTimeout=5 -o BatchMode=yes "$node" "echo ok" &>/dev/null
}

run_on_node() {
    local node=$1
    shift
    ssh -o ConnectTimeout=10 "$node" "$@" 2>/dev/null
}

# Check 1: RAPL sysfs exists
check_rapl_exists() {
    local node=$1
    log_info "[$node] Checking RAPL sysfs..."
    
    if run_on_node "$node" "test -d /sys/class/powercap/intel-rapl"; then
        log_pass "[$node] RAPL sysfs exists at /sys/class/powercap/intel-rapl"
        return 0
    else
        log_fail "[$node] RAPL sysfs NOT found - power monitoring will not work"
        return 1
    fi
}

# Check 2: RAPL domains available
check_rapl_domains() {
    local node=$1
    log_info "[$node] Checking RAPL domains..."
    
    local domains
    domains=$(run_on_node "$node" "ls -d /sys/class/powercap/intel-rapl/intel-rapl:* 2>/dev/null | wc -l" || echo "0")
    
    if [[ "$domains" -gt 0 ]]; then
        log_pass "[$node] $domains RAPL domain(s) found"
        
        # List domains
        local domain_names
        domain_names=$(run_on_node "$node" "
            for d in /sys/class/powercap/intel-rapl/intel-rapl:*/name; do
                echo -n \"\$(cat \$d 2>/dev/null) \"
            done
        " || echo "unknown")
        log_info "[$node] Domains: $domain_names"
        return 0
    else
        log_fail "[$node] No RAPL domains found"
        return 1
    fi
}

# Check 3: RAPL energy counter readable
check_rapl_readable() {
    local node=$1
    log_info "[$node] Checking RAPL energy counter access..."
    
    local energy_file="/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    
    # Try reading without sudo first
    local energy
    energy=$(run_on_node "$node" "cat $energy_file 2>/dev/null" || echo "")
    
    if [[ -n "$energy" && "$energy" =~ ^[0-9]+$ ]]; then
        log_pass "[$node] RAPL energy counter readable (no sudo): $energy µJ"
        return 0
    fi
    
    # Try with sudo
    energy=$(run_on_node "$node" "sudo cat $energy_file 2>/dev/null" || echo "")
    
    if [[ -n "$energy" && "$energy" =~ ^[0-9]+$ ]]; then
        log_warn "[$node] RAPL energy counter readable (requires sudo): $energy µJ"
        log_info "[$node] Kepler may need privileged access or powercap permissions"
        return 0
    else
        log_fail "[$node] RAPL energy counter NOT readable"
        return 1
    fi
}

# Check 4: RAPL counter incrementing (functional check)
check_rapl_functional() {
    local node=$1
    log_info "[$node] Checking RAPL counter is functional..."
    
    local result
    result=$(run_on_node "$node" "
        E1=\$(sudo cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj 2>/dev/null || echo 0)
        sleep 1
        E2=\$(sudo cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj 2>/dev/null || echo 0)
        DELTA=\$((E2 - E1))
        if [ \$DELTA -gt 0 ]; then
            echo \"OK:\$DELTA\"
        elif [ \$DELTA -lt 0 ]; then
            # Counter wrapped, still functional
            echo \"OK:wrapped\"
        else
            echo \"STUCK:0\"
        fi
    " || echo "ERROR")
    
    if [[ "$result" == OK:* ]]; then
        local delta="${result#OK:}"
        if [[ "$delta" == "wrapped" ]]; then
            log_pass "[$node] RAPL counter functional (wrapped during test)"
        else
            local watts=$((delta / 1000000))  # µJ/s = µW, /1M = W
            log_pass "[$node] RAPL counter functional (~${watts}W measured in 1s)"
        fi
        ((RAPL_AVAILABLE_COUNT++))
        return 0
    else
        log_fail "[$node] RAPL counter NOT functional or stuck"
        ((RAPL_UNAVAILABLE_COUNT++))
        return 1
    fi
}

# Check 5: Powercap permissions
check_powercap_permissions() {
    local node=$1
    log_info "[$node] Checking powercap permissions..."
    
    local perms
    perms=$(run_on_node "$node" "ls -la /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj 2>/dev/null" || echo "")
    
    if [[ -n "$perms" ]]; then
        log_info "[$node] Permissions: $perms"
        
        # Check if world-readable
        if echo "$perms" | grep -q "r--$"; then
            log_warn "[$node] RAPL not world-readable - Kepler needs privileged mode"
        elif echo "$perms" | grep -q "r--.r--"; then
            log_pass "[$node] RAPL is world-readable"
        fi
    fi
    
    return 0
}

# Check 6: CPU info for power estimation fallback
check_cpu_info() {
    local node=$1
    log_info "[$node] Checking CPU info for fallback estimation..."
    
    local cpu_model
    cpu_model=$(run_on_node "$node" "grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2 | xargs" || echo "unknown")
    
    local cpu_count
    cpu_count=$(run_on_node "$node" "nproc" || echo "0")
    
    log_info "[$node] CPU: $cpu_model ($cpu_count cores)"
    
    # Check if it's Intel (RAPL support)
    if echo "$cpu_model" | grep -qi "intel"; then
        log_pass "[$node] Intel CPU detected - RAPL should be available"
    elif echo "$cpu_model" | grep -qi "amd"; then
        log_warn "[$node] AMD CPU - RAPL may have limited support"
    else
        log_warn "[$node] Unknown CPU vendor - RAPL support uncertain"
    fi
    
    return 0
}

# Check 7: Hypervisor-specific (Scaphandre fallback)
check_hypervisor_rapl() {
    local node=$1
    log_info "[$node] Checking hypervisor RAPL for Scaphandre fallback..."
    
    # This is the fallback - if VMs don't have RAPL, hypervisor must
    check_rapl_exists "$node" || return 1
    check_rapl_domains "$node" || return 1
    check_rapl_functional "$node" || return 1
    
    # Check if Scaphandre is already installed
    if run_on_node "$node" "which scaphandre" &>/dev/null; then
        log_pass "[$node] Scaphandre already installed"
        
        # Check if running
        if run_on_node "$node" "pgrep -f scaphandre" &>/dev/null; then
            log_pass "[$node] Scaphandre is running"
        else
            log_info "[$node] Scaphandre installed but not running"
        fi
    else
        log_info "[$node] Scaphandre not installed (will be installed in Task 116)"
    fi
    
    return 0
}

# Check 8: GPU power monitoring (DCGM/nvidia-smi)
check_gpu_power() {
    local node=$1
    log_info "[$node] Checking GPU power monitoring..."
    
    if run_on_node "$node" "which nvidia-smi" &>/dev/null; then
        local gpu_power
        gpu_power=$(run_on_node "$node" "nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | head -1" || echo "")
        
        if [[ -n "$gpu_power" && "$gpu_power" != "[N/A]" ]]; then
            log_pass "[$node] GPU power reading available: ${gpu_power}W"
        else
            log_warn "[$node] GPU power reading not available (DCGM needed)"
        fi
    else
        log_info "[$node] No NVIDIA GPU or nvidia-smi not installed"
    fi
    
    return 0
}

# Run all checks on a worker node
check_worker_node() {
    local node=$1
    echo ""
    echo "========================================"
    echo "Checking worker node: $node"
    echo "========================================"
    
    if ! check_ssh "$node"; then
        log_fail "[$node] Cannot SSH to node"
        ((RAPL_UNAVAILABLE_COUNT++))
        return 1
    fi
    
    local rapl_ok=true
    check_rapl_exists "$node" || rapl_ok=false
    
    if $rapl_ok; then
        check_rapl_domains "$node" || true
        check_rapl_readable "$node" || rapl_ok=false
        check_rapl_functional "$node" || rapl_ok=false
        check_powercap_permissions "$node" || true
    fi
    
    check_cpu_info "$node" || true
    check_gpu_power "$node" || true
    
    if ! $rapl_ok; then
        log_warn "[$node] RAPL not functional - Kepler will use estimation mode"
    fi
}

# Run hypervisor checks
check_hypervisor_node() {
    local node=$1
    echo ""
    echo "========================================"
    echo "Checking HYPERVISOR: $node (Scaphandre fallback)"
    echo "========================================"
    
    if ! check_ssh "$node"; then
        log_fail "[$node] Cannot SSH to hypervisor - Scaphandre fallback unavailable!"
        return 1
    fi
    
    check_hypervisor_rapl "$node"
}

# Generate report
generate_report() {
    cat > "$REPORT_FILE" << EOF
# Power Monitoring Pre-Flight Report

**Generated**: $(date -Iseconds)

## Summary

| Metric | Count |
|--------|-------|
| Passed | $PASS_COUNT |
| Failed | $FAIL_COUNT |
| Warnings | $WARN_COUNT |
| RAPL Available | $RAPL_AVAILABLE_COUNT |
| RAPL Unavailable | $RAPL_UNAVAILABLE_COUNT |

## Power Monitoring Strategy

EOF

    if [[ $RAPL_UNAVAILABLE_COUNT -eq 0 ]]; then
        echo "✅ **All nodes have RAPL** - Kepler will use hardware counters." >> "$REPORT_FILE"
    elif [[ $RAPL_AVAILABLE_COUNT -gt 0 ]]; then
        echo "⚠️ **Mixed RAPL availability** - Some nodes will use estimation." >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "- Nodes with RAPL: $RAPL_AVAILABLE_COUNT (accurate power)" >> "$REPORT_FILE"
        echo "- Nodes without RAPL: $RAPL_UNAVAILABLE_COUNT (ML estimation)" >> "$REPORT_FILE"
    else
        echo "❌ **No RAPL in VMs** - Kepler will rely on ML estimation only." >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "**Scaphandre on hypervisor is CRITICAL** for baseline validation." >> "$REPORT_FILE"
    fi
    
    echo "" >> "$REPORT_FILE"
    echo "## Recommendation" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo "✅ **PROCEED** with Kepler deployment (Task 115)." >> "$REPORT_FILE"
    else
        echo "⚠️ **PROCEED WITH CAUTION** - Review failures before deployment." >> "$REPORT_FILE"
    fi
    
    log_info "Report saved to: $REPORT_FILE"
}

# Main
main() {
    local target="${1:-all}"
    
    echo "============================================"
    echo "Power Monitoring Pre-Flight Check (Task 115)"
    echo "============================================"
    echo ""
    
    case "$target" in
        --workers)
            for node in "${WORKERS[@]}" "${GPU_WORKERS[@]}"; do
                check_worker_node "$node"
            done
            ;;
        --hypervisor)
            check_hypervisor_node "$HYPERVISOR"
            ;;
        --all|all)
            for node in "${WORKERS[@]}" "${GPU_WORKERS[@]}"; do
                check_worker_node "$node"
            done
            check_hypervisor_node "$HYPERVISOR"
            generate_report
            ;;
        *)
            check_worker_node "$target"
            ;;
    esac
    
    echo ""
    echo "============================================"
    echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed, $WARN_COUNT warnings"
    echo "RAPL: $RAPL_AVAILABLE_COUNT available, $RAPL_UNAVAILABLE_COUNT unavailable"
    echo "============================================"
    
    # Power monitoring can work with estimation, so don't fail hard
    if [[ $RAPL_UNAVAILABLE_COUNT -gt 0 && $RAPL_AVAILABLE_COUNT -eq 0 ]]; then
        echo ""
        log_warn "No RAPL access in VMs - Kepler will use ML estimation"
        log_info "Ensure Scaphandre on hypervisor works for validation"
    fi
    
    exit 0
}

main "$@"
