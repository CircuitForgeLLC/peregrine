#!/usr/bin/env bash
# setup.sh — Peregrine dependency installer
# Installs Docker, Docker Compose v2, and (optionally) NVIDIA Container Toolkit.
# Supports: Ubuntu/Debian, Fedora/RHEL/CentOS, Arch Linux, macOS (Homebrew).
# Windows: not supported — use WSL2 with Ubuntu.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[peregrine]${NC} $*"; }
success() { echo -e "${GREEN}[peregrine]${NC} $*"; }
warn()    { echo -e "${YELLOW}[peregrine]${NC} $*"; }
error()   { echo -e "${RED}[peregrine]${NC} $*"; exit 1; }

# ── Platform detection ─────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

if [[ "$OS" == "MINGW"* ]] || [[ "$OS" == "CYGWIN"* ]] || [[ "$OS" == "MSYS"* ]]; then
    error "Windows is not supported. Please use WSL2 with Ubuntu: https://docs.microsoft.com/windows/wsl/install"
fi

DISTRO=""
DISTRO_FAMILY=""
if [[ "$OS" == "Linux" ]]; then
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        DISTRO="${ID:-unknown}"
        case "$DISTRO" in
            ubuntu|debian|linuxmint|pop)  DISTRO_FAMILY="debian" ;;
            fedora|rhel|centos|rocky|almalinux) DISTRO_FAMILY="fedora" ;;
            arch|manjaro|endeavouros)      DISTRO_FAMILY="arch" ;;
            *) warn "Unrecognised distro: $DISTRO — will attempt Debian-style install" ; DISTRO_FAMILY="debian" ;;
        esac
    fi
elif [[ "$OS" == "Darwin" ]]; then
    DISTRO_FAMILY="macos"
else
    error "Unsupported OS: $OS"
fi

info "Platform: $OS / $DISTRO_FAMILY ($ARCH)"

# ── Helpers ────────────────────────────────────────────────────────────────────
need_sudo() {
    if [[ "$EUID" -ne 0 ]]; then echo "sudo"; else echo ""; fi
}
SUDO="$(need_sudo)"

cmd_exists() { command -v "$1" &>/dev/null; }

# ── Git ────────────────────────────────────────────────────────────────────────
install_git() {
    if cmd_exists git; then success "git already installed: $(git --version)"; return; fi
    info "Installing git…"
    case "$DISTRO_FAMILY" in
        debian)  $SUDO apt-get update -q && $SUDO apt-get install -y git ;;
        fedora)  $SUDO dnf install -y git ;;
        arch)    $SUDO pacman -Sy --noconfirm git ;;
        macos)
            if cmd_exists brew; then brew install git
            else error "Homebrew not found. Install it from https://brew.sh then re-run this script."; fi ;;
    esac
    success "git installed."
}

# ── Podman detection ───────────────────────────────────────────────────────────
# If Podman is already present, skip Docker entirely and ensure podman-compose is available.
check_podman() {
    if ! cmd_exists podman; then return 1; fi
    success "Podman detected ($(podman --version)) — skipping Docker install."
    # Ensure a compose provider is available
    if podman compose version &>/dev/null 2>&1; then
        success "podman compose available."
    elif cmd_exists podman-compose; then
        success "podman-compose available."
    else
        info "Installing podman-compose…"
        case "$DISTRO_FAMILY" in
            debian)  $SUDO apt-get install -y podman-compose 2>/dev/null \
                     || pip3 install --user podman-compose ;;
            fedora)  $SUDO dnf install -y podman-compose 2>/dev/null \
                     || pip3 install --user podman-compose ;;
            arch)    $SUDO pacman -Sy --noconfirm podman-compose 2>/dev/null \
                     || pip3 install --user podman-compose ;;
            macos)   brew install podman-compose 2>/dev/null \
                     || pip3 install --user podman-compose ;;
        esac
        success "podman-compose installed."
    fi
    warn "GPU profiles (single-gpu, dual-gpu) require CDI setup:"
    warn "  sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml"
    return 0
}

# ── Docker ─────────────────────────────────────────────────────────────────────
install_docker_linux_debian() {
    $SUDO apt-get update -q
    $SUDO apt-get install -y ca-certificates curl gnupg lsb-release
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/${DISTRO}/gpg \
        | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${DISTRO} $(lsb_release -cs) stable" \
        | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
    $SUDO apt-get update -q
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO usermod -aG docker "$USER" || true
}

install_docker_linux_fedora() {
    $SUDO dnf -y install dnf-plugins-core
    $SUDO dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    $SUDO dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable --now docker
    $SUDO usermod -aG docker "$USER" || true
}

install_docker_linux_arch() {
    $SUDO pacman -Sy --noconfirm docker docker-compose
    $SUDO systemctl enable --now docker
    $SUDO usermod -aG docker "$USER" || true
}

install_docker() {
    if cmd_exists docker; then
        success "docker already installed: $(docker --version)"
        return
    fi
    info "Installing Docker…"
    case "$DISTRO_FAMILY" in
        debian)  install_docker_linux_debian ;;
        fedora)  install_docker_linux_fedora ;;
        arch)    install_docker_linux_arch ;;
        macos)
            if cmd_exists brew; then
                brew install --cask docker
                warn "Docker Desktop installed. Please open Docker Desktop and start it, then re-run this script."
                exit 0
            else
                error "Homebrew not found. Install Docker Desktop from https://docs.docker.com/desktop/mac/install/ then re-run."
            fi ;;
    esac
    success "Docker installed."
}

# ── Docker Compose v2 ──────────────────────────────────────────────────────────
check_compose() {
    # docker compose (v2) is a plugin, not a standalone binary
    if docker compose version &>/dev/null 2>&1; then
        success "Docker Compose v2 already available: $(docker compose version --short)"
    else
        warn "Docker Compose v2 not found."
        case "$DISTRO_FAMILY" in
            debian)
                $SUDO apt-get install -y docker-compose-plugin
                success "docker-compose-plugin installed." ;;
            fedora)
                $SUDO dnf install -y docker-compose-plugin
                success "docker-compose-plugin installed." ;;
            arch)
                $SUDO pacman -Sy --noconfirm docker-compose
                success "docker-compose installed." ;;
            macos)
                warn "Docker Compose ships with Docker Desktop on macOS. Ensure Docker Desktop is running." ;;
        esac
    fi
}

# ── NVIDIA Container Toolkit ───────────────────────────────────────────────────
install_nvidia_toolkit() {
    [[ "$OS" != "Linux" ]] && return   # macOS has no NVIDIA support
    if ! cmd_exists nvidia-smi; then
        info "No NVIDIA GPU detected — skipping Container Toolkit."
        return
    fi
    if docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
        success "NVIDIA Container Toolkit already working."
        return
    fi
    info "NVIDIA GPU detected. Installing Container Toolkit…"
    case "$DISTRO_FAMILY" in
        debian)
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
                | $SUDO gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
                | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
                | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
            $SUDO apt-get update -q
            $SUDO apt-get install -y nvidia-container-toolkit
            $SUDO nvidia-ctk runtime configure --runtime=docker
            $SUDO systemctl restart docker ;;
        fedora)
            curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
                | $SUDO tee /etc/yum.repos.d/nvidia-container-toolkit.repo
            $SUDO dnf install -y nvidia-container-toolkit
            $SUDO nvidia-ctk runtime configure --runtime=docker
            $SUDO systemctl restart docker ;;
        arch)
            $SUDO pacman -Sy --noconfirm nvidia-container-toolkit || \
                warn "nvidia-container-toolkit not in repos — try AUR: yay -S nvidia-container-toolkit" ;;
    esac
    success "NVIDIA Container Toolkit installed."
}

# ── Environment setup ──────────────────────────────────────────────────────────
setup_env() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        info "Created .env from .env.example — edit it to customise ports and paths."
    else
        info ".env already exists — skipping."
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Peregrine — Dependency Installer       ║${NC}"
    echo -e "${BLUE}║   by Circuit Forge LLC                   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
    echo ""

    install_git
    # Podman takes precedence if already installed; otherwise install Docker
    if ! check_podman; then
        install_docker
        check_compose
        install_nvidia_toolkit
    fi
    setup_env

    echo ""
    success "All dependencies installed."
    echo ""
    echo -e "  ${GREEN}Next steps:${NC}"
    echo -e "  1. Edit ${YELLOW}.env${NC} to set your preferred ports and model paths"
    echo -e "  2. Start Peregrine:"
    echo -e "     ${YELLOW}make start${NC}  (auto-detects Docker or Podman)"
    echo -e "  3. Open ${YELLOW}http://localhost:8501${NC} — the setup wizard will guide you"
    echo ""
    if groups "$USER" 2>/dev/null | grep -q docker; then
        true
    else
        warn "You may need to log out and back in for Docker group membership to take effect."
    fi
}

main "$@"
