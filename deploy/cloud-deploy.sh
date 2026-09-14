#!/usr/bin/env bash
# ============================================================
# 华米商城 AI 智能客服与销售助手 - 云服务器一键部署脚本
# 适用: Ubuntu 22.04 / 24.04 / Debian 12 (推荐 2核4G 起)
# 用法: bash deploy/cloud-deploy.sh
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()   { echo -e "\033[0;31m[ERROR]${NC} $*"; exit 1; }

REPO_URL="${REPO_URL:-https://github.com/01sure/Essence.git}"
APP_DIR="${APP_DIR:-/opt/huami-agent}"

# ---------- 0. 检测系统 ----------
[ "$(id -u)" -eq 0 ] || die "请用 root 运行（sudo bash deploy/cloud-deploy.sh）"
if [ -f /etc/os-release ]; then
  . /etc/os-release
  case "$ID" in
    ubuntu|debian) : ;;
    *) warn "当前系统为 $ID，脚本仅保证 Ubuntu/Debian 可用，继续尝试…" ;;
  esac
else
  die "无法识别系统版本"
fi

# ---------- 1. 安装 Docker 与 Compose ----------
if ! command -v docker >/dev/null 2>&1; then
  info "未检测到 Docker，开始安装（官方脚本，失败则回退 apt 源）…"
  curl -fsSL https://get.docker.com | sh || {
    warn "官方脚本失败，改用 apt 安装 docker.io"
    apt-get update -y
    apt-get install -y docker.io
  }
  systemctl enable --now docker || true
fi
if ! docker compose version >/dev/null 2>&1; then
  info "未检测到 docker compose 插件，正在安装…"
  apt-get update -y
  apt-get install -y docker-compose-plugin || {
    warn "apt 安装 compose 插件失败，尝试 pip 安装 docker-compose"
    apt-get install -y python3-pip
    pip3 install -q docker-compose
    # 提供 docker-compose 兼容命令
    if ! command -v docker-compose >/dev/null 2>&1; then
      echo '#!/bin/sh' > /usr/local/bin/docker-compose
      echo 'exec docker compose "$@"' >> /usr/local/bin/docker-compose
      chmod +x /usr/local/bin/docker-compose
    fi
  }
fi
docker --version && docker compose version

# ---------- 2. 获取代码 ----------
if [ -f "$PWD/docker-compose.yml" ]; then
  APP_DIR="$PWD"
  info "检测到当前目录即为项目根目录：$APP_DIR"
else
  if [ ! -d "$APP_DIR" ]; then
    info "克隆项目到 $APP_DIR …"
    git clone --depth 1 "$REPO_URL" "$APP_DIR"
  else
    info "目录 $APP_DIR 已存在，拉取最新代码…"
    git -C "$APP_DIR" pull --ff-only || warn "pull 失败，继续使用现有代码"
  fi
  cd "$APP_DIR"
fi

# ---------- 3. 生成环境变量与密钥 ----------
if [ ! -f .env ]; then
  MYSQL_ROOT_PASSWORD=$(openssl rand -hex 12)
  MYSQL_PASSWORD=$(openssl rand -hex 12)
  cat > .env <<EOF
HTTP_PORT=80
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
MYSQL_PASSWORD=${MYSQL_PASSWORD}
ES_JAVA_OPTS=-Xms1g -Xmx1g
EOF
  info ".env 已生成（MySQL 密码为随机值，见 $APP_DIR/.env）"
else
  info ".env 已存在，保留原配置"
fi

if [ ! -f backend/.env ]; then
  SECRET_KEY=$(openssl rand -hex 32)
  cat > backend/.env <<EOF
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=${LLM_API_KEY:-}
LLM_MODEL=deepseek-chat
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=${EMBEDDING_API_KEY:-}
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
ES_URL=http://elasticsearch:9200
ES_USERNAME=
ES_PASSWORD=
ES_INDEX_KB=huami_kb
ES_INDEX_PRODUCTS=huami_products
DATABASE_URL=mysql+aiomysql://huami:${MYSQL_PASSWORD:-huami123}@mysql:3306/huami_agent?charset=utf8mb4
SECRET_KEY=${SECRET_KEY}
ENV=prod
CORS_ORIGINS=*
RATE_LIMIT_PER_MIN=30
HUMAN_HANDOFF_KEYWORDS=人工,真人,客服人员,转接人工,投诉到哪,打电话
EOF
  info "backend/.env 已生成（SECRET_KEY 随机 64 位）"
  if [ -z "${LLM_API_KEY:-}" ]; then
    warn "LLM_API_KEY 未设置：AI 对话将以降级模式运行（无 LLM 调用）。"
    warn "如需完整演示，请编辑 backend/.env 填入 LLM_API_KEY（DeepSeek）与 EMBEDDING_API_KEY（硅基流动），然后 docker compose restart backend"
  fi
else
  info "backend/.env 已存在，保留原配置"
fi

# ---------- 4. 构建并启动 ----------
info "开始构建镜像并启动（首次构建 ES+IK 与前端约 5-10 分钟）…"
docker compose up -d --build

# ---------- 5. 健康检查 ----------
info "等待服务就绪（最长 180 秒）…"
for i in $(seq 1 36); do
  if curl -sf -o /dev/null http://127.0.0.1/api/health; then
    break
  fi
  sleep 5
done

PUBLIC_IP=$(curl -sf --max-time 5 https://api.ipify.org || curl -sf --max-time 5 https://ifconfig.me || echo "<服务器IP>")

echo
info "================ 部署完成 ================"
echo -e "  管理后台:   ${GREEN}http://${PUBLIC_IP}/admin${NC}  （默认账号 admin / admin123，请尽快修改）"
echo -e "  聊天演示:   ${GREEN}http://${PUBLIC_IP}/widget/demo.html${NC}"
echo -e "  健康检查:   ${GREEN}http://${PUBLIC_IP}/api/health${NC}"
echo -e "  查看日志:   ${GREEN}docker compose -f $APP_DIR/docker-compose.yml logs -f backend${NC}"
echo "=========================================="
if curl -sf -o /dev/null http://127.0.0.1/api/health; then
  info "健康检查通过"
else
  warn "健康检查未通过，请执行：docker compose logs backend 查看初始化日志"
fi
