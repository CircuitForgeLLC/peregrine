#!/usr/bin/env bash
# install.sh — Peregrine dependency installer
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

# ── Build tools (make, etc.) ───────────────────────────────────────────────────
install_build_tools() {
    if cmd_exists make; then success "make already installed: $(make --version | head -1)"; return; fi
    info "Installing build tools (make)…"
    case "$DISTRO_FAMILY" in
        debian)  $SUDO apt-get update -q && $SUDO apt-get install -y make ;;
        fedora)  $SUDO dnf install -y make ;;
        arch)    $SUDO pacman -Sy --noconfirm make ;;
        macos)
            if cmd_exists brew; then brew install make
            else error "Homebrew not found. Install it from https://brew.sh then re-run this script."; fi ;;
    esac
    success "make installed."
}

# ── Git safe.directory ─────────────────────────────────────────────────────────
# Git 2.35.2+ rejects repos where the directory owner != current user.
# Common when cloned as root into /opt and then run as a regular user.
# Fix by registering the repo path in the appropriate user's git config.
configure_git_safe_dir() {
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # If git is happy already, nothing to do
    if git -C "$repo_dir" rev-parse --git-dir &>/dev/null 2>&1; then
        success "Git repository ownership OK."
        return
    fi

    info "Configuring git safe.directory for $repo_dir…"
    if [[ -n "${SUDO_USER:-}" ]]; then
        # Running under sudo — write into the invoking user's config, not root's
        sudo -u "$SUDO_USER" git config --global --add safe.directory "$repo_dir"
        success "safe.directory set for user '${SUDO_USER}'."
    else
        git config --global --add safe.directory "$repo_dir"
        success "safe.directory set."
    fi
}

activate_git_hooks() {
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -d "$repo_dir/.githooks" ]]; then
        git -C "$repo_dir" config core.hooksPath .githooks
        success "Git hooks activated (.githooks/)."
    fi
}

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
    if [[ "$OS" != "Darwin" ]]; then
        warn "GPU profiles (single-gpu, dual-gpu) require CDI setup:"
        warn "  sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml"
    fi
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

# ── Docker daemon health check ──────────────────────────────────────────────────
check_docker_running() {
    if docker info &>/dev/null 2>&1; then
        success "Docker daemon is running."
        return
    fi
    warn "Docker daemon is not responding."
    if [[ "$OS" == "Linux" ]] && command -v systemctl &>/dev/null; then
        info "Starting Docker service…"
        $SUDO systemctl start docker 2>/dev/null || true
        sleep 2
        if docker info &>/dev/null 2>&1; then
            success "Docker daemon started."
        else
            warn "Docker failed to start. Run: sudo systemctl start docker"
        fi
    elif [[ "$OS" == "Darwin" ]]; then
        warn "Docker Desktop is not running. Start it, wait for the whale icon, then run 'make start'."
    fi
}

# ── NVIDIA Container Toolkit ───────────────────────────────────────────────────
install_nvidia_toolkit() {
    [[ "$OS" != "Linux" ]] && return   # macOS has no NVIDIA support
    if ! cmd_exists nvidia-smi; then
        info "No NVIDIA GPU detected — skipping Container Toolkit."
        return
    fi
    if cmd_exists nvidia-ctk && nvidia-ctk runtime validate --runtime=docker &>/dev/null 2>&1; then
        success "NVIDIA Container Toolkit already configured."
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

# ── Ollama (macOS native) ──────────────────────────────────────────────────────
# On macOS, Docker Desktop runs in a Linux VM that cannot access the Apple GPU.
# Ollama must run natively on the host to use Metal GPU acceleration.
# When it's running on :11434, preflight automatically adopts it and stubs out
# the Docker Ollama container so there's no conflict.
install_ollama_macos() {
    [[ "$OS" != "Darwin" ]] && return
    echo ""
    info "Ollama (native macOS — enables Apple Silicon Metal GPU acceleration)"
    echo -e "  Docker cannot pass through the Apple GPU. For GPU-accelerated inference,"
    echo -e "  Ollama must run natively on the host."
    echo ""

    if cmd_exists ollama; then
        success "Ollama already installed: $(ollama --version 2>/dev/null | head -1 || echo 'unknown version')"
        if pgrep -x ollama &>/dev/null || launchctl print gui/"$(id -u)" 2>/dev/null | grep -q com.ollama; then
            success "Ollama service is running — preflight will adopt it automatically."
        else
            warn "Ollama is installed but not running."
            warn "Start it with:  brew services start ollama   (or: ollama serve)"
        fi
        return
    fi

    # Non-interactive (e.g. curl | bash) — skip prompt
    if [[ ! -t 0 ]]; then
        warn "Non-interactive — skipping Ollama install."
        warn "Install manually: brew install ollama && brew services start ollama"
        return
    fi

    read -rp "  Install Ollama natively for Metal GPU support? [Y/n]: " yn
    yn="${yn:-Y}"
    if [[ "$yn" =~ ^[Yy] ]]; then
        if cmd_exists brew; then
            brew install ollama
            brew services start ollama
            success "Ollama installed and started."
            success "Preflight will adopt it on next run — no Docker Ollama container will start."
        else
            warn "Homebrew not found."
            warn "Install Ollama manually from https://ollama.com/download/mac then start it."
        fi
    else
        info "Skipped. The 'cpu' profile will use Docker Ollama on CPU instead."
    fi
}

# ── Environment setup ──────────────────────────────────────────────────────────
# Note: Ollama runs as a Docker container — the compose.yml ollama service
# handles model download automatically on first start (see docker/ollama/entrypoint.sh).
setup_env() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        info "Created .env from .env.example — edit it to customise ports and paths."
    else
        info ".env already exists — skipping."
    fi
}

# ── License key (optional) ────────────────────────────────────────────────────
capture_license_key() {
    [[ ! -t 0 ]] && return   # skip in non-interactive installs (curl | bash)
    local env_file
    env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"
    [[ ! -f "$env_file" ]] && return   # setup_env() creates it; nothing to write into yet

    echo ""
    info "License key (optional)"
    echo -e "  Peregrine works without a key for personal self-hosted use."
    echo -e "  Paid-tier users: enter your ${YELLOW}CFG-XXXX-…${NC} key to unlock cloud LLM and integrations."
    echo ""
    read -rp "  CircuitForge license key [press Enter to skip]: " _key || true
    if [[ -n "$_key" ]]; then
        if echo "$_key" | grep -qE '^CFG-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$'; then
            _update_env_key "$env_file" "CF_LICENSE_KEY" "$_key"
            _update_env_key "$env_file" "HEIMDALL_URL" "https://license.circuitforge.tech"
            success "License key saved — paid-tier features enabled."
        else
            warn "Key format looks wrong (expected CFG-XXXX-AAAA-BBBB-CCCC) — skipping."
            info "Add it manually to .env as CF_LICENSE_KEY= later."
        fi
    fi
}

# ── Model weights storage ───────────────────────────────────────────────────────
_update_env_key() {
    # Portable in-place key=value update for .env files (Linux + macOS).
    # Appends the key if not already present.
    local file="$1" key="$2" val="$3"
    awk -v k="$key" -v v="$val" '
        BEGIN { found=0 }
        $0 ~ ("^" k "=") { print k "=" v; found=1; next }
        { print }
        END { if (!found) print k "=" v }
    ' "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
}

configure_model_paths() {
    local env_file
    env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"

    # Skip prompts when stdin is not a terminal (e.g. curl | bash)
    if [[ ! -t 0 ]]; then
        info "Non-interactive — using default model paths from .env"
        return
    fi

    echo ""
    info "Model weights storage"
    echo -e "  AI models can be 2–30+ GB each. If you have a separate data drive,"
    echo -e "  point these at it now. Press Enter to keep the value shown in [brackets]."
    echo ""

    local current input

    current="$(grep -E '^OLLAMA_MODELS_DIR=' "$env_file" 2>/dev/null | cut -d= -f2-)"
    [[ -z "$current" ]] && current="~/models/ollama"
    read -rp "  Ollama models dir [${current}]: " input || input=""
    input="${input:-$current}"
    input="${input/#\~/$HOME}"
    mkdir -p "$input" 2>/dev/null || warn "Could not create $input — ensure it exists before 'make start'"
    _update_env_key "$env_file" "OLLAMA_MODELS_DIR" "$input"
    success "OLLAMA_MODELS_DIR=$input"

    current="$(grep -E '^VLLM_MODELS_DIR=' "$env_file" 2>/dev/null | cut -d= -f2-)"
    [[ -z "$current" ]] && current="~/models/vllm"
    read -rp "  vLLM models dir   [${current}]: " input || input=""
    input="${input:-$current}"
    input="${input/#\~/$HOME}"
    mkdir -p "$input" 2>/dev/null || warn "Could not create $input — ensure it exists before 'make start'"
    _update_env_key "$env_file" "VLLM_MODELS_DIR" "$input"
    success "VLLM_MODELS_DIR=$input"

    echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Peregrine — Dependency Installer                   ║${NC}"
    echo -e "${BLUE}║   by Circuit Forge LLC                               ║${NC}"
    echo -e "${BLUE}║   \"Don't be evil, for real and forever.\"             ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""

    install_build_tools
    install_git
    configure_git_safe_dir
    activate_git_hooks
    # Podman takes precedence if already installed; otherwise install Docker
    if ! check_podman; then
        install_docker
        check_docker_running
        check_compose
        install_nvidia_toolkit
    fi
    install_ollama_macos
    setup_env
    capture_license_key
    configure_model_paths

    # Read the actual port from .env so next-steps reflects any customisation
    local _script_dir _port
    _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    _port="$(grep -E '^STREAMLIT_PORT=' "$_script_dir/.env" 2>/dev/null | cut -d= -f2-)"
    _port="${_port:-8502}"

    echo ""
    success "All dependencies installed."
    echo ""
    echo -e "  ${GREEN}Next steps:${NC}"
    echo -e "  1. Start Peregrine:"
    echo -e "     ${YELLOW}./manage.sh start${NC}                    # remote/API-only (no local GPU)"
    if [[ "$OS" == "Darwin" ]] && cmd_exists ollama; then
        echo -e "     ${YELLOW}./manage.sh start --profile cpu${NC}      # local Ollama inference (Metal GPU via native Ollama)"
    else
        echo -e "     ${YELLOW}./manage.sh start --profile cpu${NC}      # local Ollama inference (CPU)"
    fi
    echo -e "  2. Open ${YELLOW}http://localhost:${_port}${NC} — the setup wizard will guide you"
    echo -e "  (Tip: edit ${YELLOW}.env${NC} any time to adjust ports or model paths)"
    echo ""
    if groups "$USER" 2>/dev/null | grep -q docker; then
        true
    else
        warn "You may need to log out and back in for Docker group membership to take effect."
    fi
}

main "$@"
