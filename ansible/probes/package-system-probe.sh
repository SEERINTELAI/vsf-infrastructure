#!/bin/bash
# Package System Probe for VM deployment
# Creates a tarball with all necessary files for deploying to VSF VMs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZDC_PATH="${ZDC_PATH:-/home/dan/ASIT/repos/Zon-data-center}"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/dist}"
VERSION=$(cat "$ZDC_PATH/VERSION" 2>/dev/null || echo "1.0.0")
PACKAGE_NAME="system-probe-vm-${VERSION}"

echo "=== System Probe VM Packager ==="
echo "Source: $ZDC_PATH"
echo "Output: $OUTPUT_DIR"
echo "Version: $VERSION"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Create temporary staging area
STAGING_DIR=$(mktemp -d)
PROBE_DIR="$STAGING_DIR/$PACKAGE_NAME"
mkdir -p "$PROBE_DIR"

echo "Staging to: $STAGING_DIR"

# Copy MCP server
echo "Copying mcp_server..."
cp -r "$ZDC_PATH/mcp_server" "$PROBE_DIR/"

# Copy probe utilities
echo "Copying probe utilities..."
cp -r "$ZDC_PATH/probe" "$PROBE_DIR/"

# Copy service management
echo "Copying service scripts..."
cp "$ZDC_PATH/probe.sh" "$PROBE_DIR/"
cp "$ZDC_PATH/zon-cli.py" "$PROBE_DIR/"

# Copy requirements (VM-specific, minimal)
echo "Creating VM-specific requirements..."
cat > "$PROBE_DIR/requirements.txt" << 'EOF'
# System Probe for VM - Minimal Requirements
psutil>=5.9.0
watchdog>=3.0.0

# MCP dependencies
fastmcp==2.14.1
fastapi==0.128.0
starlette==0.50.0
anyio==4.12.0
mcp[cli]==1.25.0
mcp==1.25.0

# Rich terminal output
rich==14.2.0
EOF

# Create VERSION file
echo "$VERSION" > "$PROBE_DIR/VERSION"

# Create VM-specific config template
cat > "$PROBE_DIR/vm-config.template" << 'EOF'
# VM System Probe Configuration
# Rename to config.env and set appropriate values

# Hostname (will be auto-detected if not set)
PROBE_HOSTNAME=

# MCP Server port
MCP_PORT=8765

# n8n webhook for registration (optional)
N8N_WEBHOOK_URL=

# Disable GPU features (no real GPU in VM)
DISABLE_GPU=true

# Disable RAPL power monitoring (not available in VM)
DISABLE_RAPL=true
EOF

# Create VM-specific startup script
cat > "$PROBE_DIR/start-probe-vm.sh" << 'EOF'
#!/bin/bash
# Start System Probe on VM
# Detects hostname and starts MCP server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load config if exists
if [ -f "config.env" ]; then
    source config.env
fi

# Auto-detect hostname
if [ -z "$PROBE_HOSTNAME" ]; then
    PROBE_HOSTNAME=$(hostname)
fi

# Create hostname.secret
echo "$PROBE_HOSTNAME" > hostname.secret

# Set environment
export DISABLE_GPU=${DISABLE_GPU:-true}
export DISABLE_RAPL=${DISABLE_RAPL:-true}
export MCP_PORT=${MCP_PORT:-8765}

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Start MCP server
echo "Starting System Probe MCP Server on port $MCP_PORT..."
exec python3 -m mcp_server.zon_mcp_server --port $MCP_PORT
EOF

chmod +x "$PROBE_DIR/start-probe-vm.sh"

# Create systemd service template
cat > "$PROBE_DIR/system-probe.service.template" << 'EOF'
[Unit]
Description=System Probe MCP Server
After=network.target

[Service]
Type=simple
User=probe
Group=probe
WorkingDirectory=/opt/system-probe
ExecStart=/opt/system-probe/venv/bin/python3 -m mcp_server.zon_mcp_server --port 8765
Restart=always
RestartSec=10
Environment=DISABLE_GPU=true
Environment=DISABLE_RAPL=true

[Install]
WantedBy=multi-user.target
EOF

# Create installation script
cat > "$PROBE_DIR/install.sh" << 'EOF'
#!/bin/bash
# Install System Probe on VM

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/system-probe}"
PROBE_USER="${PROBE_USER:-probe}"

echo "=== System Probe VM Installer ==="
echo "Install directory: $INSTALL_DIR"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Create probe user if doesn't exist
if ! id "$PROBE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$PROBE_USER"
    echo "Created user: $PROBE_USER"
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Copy files
cp -r . "$INSTALL_DIR/"

# Create hostname.secret
hostname > "$INSTALL_DIR/hostname.secret"

# Create virtual environment
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Set ownership
chown -R "$PROBE_USER:$PROBE_USER" "$INSTALL_DIR"

# Install systemd service
cp system-probe.service.template /etc/systemd/system/system-probe.service
systemctl daemon-reload
systemctl enable system-probe

echo ""
echo "Installation complete!"
echo ""
echo "To start the probe:"
echo "  sudo systemctl start system-probe"
echo ""
echo "To check status:"
echo "  sudo systemctl status system-probe"
echo ""
echo "MCP endpoint: http://$(hostname):8765/mcp"
EOF

chmod +x "$PROBE_DIR/install.sh"

# Create the tarball
echo ""
echo "Creating tarball..."
cd "$STAGING_DIR"
tar -czf "$OUTPUT_DIR/$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

# Cleanup
rm -rf "$STAGING_DIR"

echo ""
echo "=== Package Created ==="
echo "Output: $OUTPUT_DIR/$PACKAGE_NAME.tar.gz"
echo ""
echo "To deploy:"
echo "  1. Copy tarball to target VM"
echo "  2. Extract: tar -xzf $PACKAGE_NAME.tar.gz"
echo "  3. Install: cd $PACKAGE_NAME && sudo ./install.sh"
echo ""
