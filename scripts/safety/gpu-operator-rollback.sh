#!/bin/bash
#
# gpu-operator-rollback.sh - Rollback NVIDIA GPU Operator deployment
#
# Use this script to safely revert GPU Operator if deployment fails or
# causes issues. Preserves GPU functionality by restoring to pre-deployment state.
#
# Usage:
#   ./gpu-operator-rollback.sh                    # Full rollback
#   ./gpu-operator-rollback.sh --check            # Check current state only
#   ./gpu-operator-rollback.sh --operator-only    # Remove operator, keep drivers
#   ./gpu-operator-rollback.sh --emergency        # Force cleanup (destructive)
#
# Requirements:
#   - kubectl access to cluster
#   - Helm if operator was installed via Helm
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/gpu-rollback-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="${SCRIPT_DIR}/gpu-operator-backup-$(date +%Y%m%d-%H%M%S)"

# GPU Operator namespace and release
GPU_OPERATOR_NS="${GPU_OPERATOR_NS:-gpu-operator}"
GPU_OPERATOR_RELEASE="${GPU_OPERATOR_RELEASE:-gpu-operator}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    local msg="[$(date -Iseconds)] $1"
    echo -e "$msg" | tee -a "$LOG_FILE"
}

log_pass() { log "${GREEN}[OK]${NC} $1"; }
log_fail() { log "${RED}[FAIL]${NC} $1"; }
log_warn() { log "${YELLOW}[WARN]${NC} $1"; }
log_info() { log "[INFO] $1"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &>/dev/null; then
        log_fail "kubectl not found"
        exit 1
    fi
    
    if ! kubectl cluster-info &>/dev/null; then
        log_fail "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_pass "Prerequisites OK"
}

# Backup current state
backup_current_state() {
    log_info "Backing up current GPU Operator state to $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    
    # Backup namespace resources
    kubectl get all -n "$GPU_OPERATOR_NS" -o yaml > "$BACKUP_DIR/all-resources.yaml" 2>/dev/null || true
    
    # Backup CRDs
    kubectl get clusterpolicies.nvidia.com -o yaml > "$BACKUP_DIR/clusterpolicies.yaml" 2>/dev/null || true
    kubectl get nvidiadrivers.nvidia.com -o yaml > "$BACKUP_DIR/nvidiadrivers.yaml" 2>/dev/null || true
    
    # Backup Helm values if installed via Helm
    if command -v helm &>/dev/null; then
        helm get values "$GPU_OPERATOR_RELEASE" -n "$GPU_OPERATOR_NS" > "$BACKUP_DIR/helm-values.yaml" 2>/dev/null || true
        helm get manifest "$GPU_OPERATOR_RELEASE" -n "$GPU_OPERATOR_NS" > "$BACKUP_DIR/helm-manifest.yaml" 2>/dev/null || true
    fi
    
    # Backup node labels
    kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels}{"\n"}{end}' > "$BACKUP_DIR/node-labels.txt" 2>/dev/null || true
    
    log_pass "Backup saved to $BACKUP_DIR"
}

# Check current GPU Operator state
check_current_state() {
    log_info "Checking current GPU Operator state..."
    
    echo ""
    echo "=== Namespace: $GPU_OPERATOR_NS ==="
    if kubectl get namespace "$GPU_OPERATOR_NS" &>/dev/null; then
        kubectl get pods -n "$GPU_OPERATOR_NS" --no-headers 2>/dev/null || echo "No pods"
    else
        log_info "Namespace $GPU_OPERATOR_NS does not exist"
    fi
    
    echo ""
    echo "=== GPU Operator CRDs ==="
    kubectl get crd | grep nvidia || echo "No NVIDIA CRDs found"
    
    echo ""
    echo "=== ClusterPolicy ==="
    kubectl get clusterpolicies.nvidia.com 2>/dev/null || echo "No ClusterPolicy"
    
    echo ""
    echo "=== GPU Nodes ==="
    kubectl get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null || echo "No GPU nodes labeled"
    
    echo ""
    echo "=== GPU Resources ==="
    kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}' 2>/dev/null | grep -v "^$" || echo "No GPU resources"
}

# Remove GPU Operator via Helm
remove_helm_release() {
    log_info "Removing GPU Operator Helm release..."
    
    if ! command -v helm &>/dev/null; then
        log_warn "Helm not found, skipping Helm uninstall"
        return 1
    fi
    
    if helm list -n "$GPU_OPERATOR_NS" | grep -q "$GPU_OPERATOR_RELEASE"; then
        helm uninstall "$GPU_OPERATOR_RELEASE" -n "$GPU_OPERATOR_NS" --wait --timeout 5m
        log_pass "Helm release $GPU_OPERATOR_RELEASE uninstalled"
        return 0
    else
        log_info "Helm release $GPU_OPERATOR_RELEASE not found"
        return 1
    fi
}

# Remove ClusterPolicy
remove_cluster_policy() {
    log_info "Removing ClusterPolicy..."
    
    local policies
    policies=$(kubectl get clusterpolicies.nvidia.com -o name 2>/dev/null || echo "")
    
    if [[ -n "$policies" ]]; then
        for policy in $policies; do
            kubectl delete "$policy" --timeout=60s || true
        done
        log_pass "ClusterPolicy removed"
    else
        log_info "No ClusterPolicy found"
    fi
}

# Remove GPU Operator namespace
remove_namespace() {
    log_info "Removing GPU Operator namespace..."
    
    if kubectl get namespace "$GPU_OPERATOR_NS" &>/dev/null; then
        # First, remove finalizers from stuck resources
        for resource in $(kubectl get all -n "$GPU_OPERATOR_NS" -o name 2>/dev/null); do
            kubectl patch "$resource" -n "$GPU_OPERATOR_NS" -p '{"metadata":{"finalizers":null}}' --type=merge 2>/dev/null || true
        done
        
        kubectl delete namespace "$GPU_OPERATOR_NS" --timeout=120s --wait=true || true
        
        # Wait for namespace deletion
        local timeout=60
        while kubectl get namespace "$GPU_OPERATOR_NS" &>/dev/null && [[ $timeout -gt 0 ]]; do
            sleep 2
            ((timeout -= 2))
        done
        
        if kubectl get namespace "$GPU_OPERATOR_NS" &>/dev/null; then
            log_warn "Namespace still exists - may need manual cleanup"
        else
            log_pass "Namespace $GPU_OPERATOR_NS removed"
        fi
    else
        log_info "Namespace $GPU_OPERATOR_NS does not exist"
    fi
}

# Remove NVIDIA CRDs
remove_crds() {
    log_info "Removing NVIDIA CRDs..."
    
    local crds
    crds=$(kubectl get crd -o name | grep nvidia || echo "")
    
    if [[ -n "$crds" ]]; then
        for crd in $crds; do
            kubectl delete "$crd" --timeout=30s || true
        done
        log_pass "NVIDIA CRDs removed"
    else
        log_info "No NVIDIA CRDs found"
    fi
}

# Remove node labels
remove_node_labels() {
    log_info "Removing GPU Operator node labels..."
    
    local gpu_nodes
    gpu_nodes=$(kubectl get nodes -l nvidia.com/gpu.present=true -o name 2>/dev/null || echo "")
    
    if [[ -n "$gpu_nodes" ]]; then
        for node in $gpu_nodes; do
            kubectl label "$node" nvidia.com/gpu.present- 2>/dev/null || true
            kubectl label "$node" nvidia.com/cuda.driver.major- 2>/dev/null || true
            kubectl label "$node" nvidia.com/cuda.driver.minor- 2>/dev/null || true
            kubectl label "$node" nvidia.com/cuda.runtime.major- 2>/dev/null || true
            kubectl label "$node" nvidia.com/gfd.timestamp- 2>/dev/null || true
        done
        log_pass "Node labels removed"
    else
        log_info "No labeled GPU nodes found"
    fi
}

# Validate GPU still works after rollback
validate_gpu_access() {
    log_info "Validating GPU access on nodes..."
    
    local gpu_workers=(vsf-gpu-1 vsf-gpu-2 vsf-gpu-3 vsf-gpu-4 vsf-gpu-5 vsf-gpu-6 vsf-gpu-7 vsf-gpu-8)
    local success=0
    local failed=0
    
    for node in "${gpu_workers[@]}"; do
        if ssh -o ConnectTimeout=5 "$node" "nvidia-smi --query-gpu=name --format=csv,noheader" &>/dev/null; then
            ((success++))
        else
            ((failed++))
            log_warn "GPU access failed on $node"
        fi
    done
    
    log_info "GPU validation: $success succeeded, $failed failed"
    
    if [[ $failed -eq 0 ]]; then
        log_pass "All GPUs accessible after rollback"
    else
        log_warn "Some GPUs may have issues - check manually"
    fi
}

# Emergency cleanup (destructive)
emergency_cleanup() {
    log_warn "EMERGENCY CLEANUP - This is destructive!"
    echo ""
    read -p "Are you sure you want to proceed? (type 'yes' to confirm): " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        log_info "Aborted"
        exit 0
    fi
    
    log_info "Starting emergency cleanup..."
    
    # Force delete all resources in namespace
    kubectl delete all --all -n "$GPU_OPERATOR_NS" --force --grace-period=0 2>/dev/null || true
    
    # Remove finalizers from namespace
    kubectl patch namespace "$GPU_OPERATOR_NS" -p '{"metadata":{"finalizers":null}}' --type=merge 2>/dev/null || true
    kubectl delete namespace "$GPU_OPERATOR_NS" --force --grace-period=0 2>/dev/null || true
    
    # Remove CRDs forcefully
    for crd in $(kubectl get crd -o name | grep nvidia 2>/dev/null); do
        kubectl patch "$crd" -p '{"metadata":{"finalizers":null}}' --type=merge 2>/dev/null || true
        kubectl delete "$crd" --force --grace-period=0 2>/dev/null || true
    done
    
    log_pass "Emergency cleanup complete"
}

# Full rollback
full_rollback() {
    log_info "Starting full GPU Operator rollback..."
    
    backup_current_state
    remove_helm_release || true
    remove_cluster_policy
    remove_namespace
    remove_crds
    remove_node_labels
    validate_gpu_access
    
    log_pass "Rollback complete"
    log_info "Backup saved to: $BACKUP_DIR"
    log_info "Log saved to: $LOG_FILE"
}

# Operator-only rollback (keep drivers)
operator_only_rollback() {
    log_info "Removing GPU Operator (keeping drivers)..."
    
    backup_current_state
    remove_helm_release || true
    remove_cluster_policy
    
    # Don't remove namespace or CRDs to preserve driver state
    log_pass "Operator removed, drivers preserved"
    log_info "To fully clean up, run: $0 --full"
}

# Main
main() {
    local mode="${1:---full}"
    
    echo "============================================"
    echo "GPU Operator Rollback Script"
    echo "============================================"
    echo ""
    
    check_prerequisites
    
    case "$mode" in
        --check)
            check_current_state
            ;;
        --operator-only)
            operator_only_rollback
            ;;
        --emergency)
            emergency_cleanup
            ;;
        --full|*)
            full_rollback
            ;;
    esac
}

main "$@"
