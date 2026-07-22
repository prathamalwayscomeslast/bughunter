#!/usr/bin/env bash
# shellcheck disable=SC2154   # Variables are injected by Terraform templatefile()
# Runs once on first boot as root.
# Bootstraps the BugHunter ARQ worker on Amazon Linux 2023.
set -euo pipefail

# ── System packages ──────────────────────────────────────────────────────────
dnf update -y
dnf install -y python3.11 python3.11-pip git docker

systemctl enable --now docker
usermod -aG docker ec2-user

# ── App directory ────────────────────────────────────────────────────────────
mkdir -p /opt/bughunter
chown ec2-user:ec2-user /opt/bughunter

# Decode and write the GitHub App private key
echo "${github_private_key_b64}" | base64 -d > /opt/bughunter/bughunter.private-key.pem
chmod 600 /opt/bughunter/bughunter.private-key.pem
chown ec2-user:ec2-user /opt/bughunter/bughunter.private-key.pem

# ── Environment file read by the systemd service ─────────────────────────────
cat > /opt/bughunter/.env <<ENVEOF
REDIS_URL=${redis_url}
DATABASE_URL=${database_url}
WEBHOOK_SECRET=${webhook_secret}
GITHUB_APP_ID=${github_app_id}
GITHUB_PRIVATE_KEY_PATH=/opt/bughunter/bughunter.private-key.pem
ENVEOF
chmod 600 /opt/bughunter/.env
chown ec2-user:ec2-user /opt/bughunter/.env

# ── Clone repo & install deps ─────────────────────────────────────────────────
# The deploy workflow will handle subsequent updates via SSH + git pull.
# This first run just gets the service up for the very first boot.
sudo -u ec2-user bash <<'SETUP'
  cd /opt/bughunter
  git clone https://github.com/prathamalwayscomeslast/bughunter.git repo
  cd repo/orchestrator
  python3.11 -m pip install --user -r requirements.txt
SETUP

# ── systemd service ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/bughunter-worker.service <<'SVCEOF'
[Unit]
Description=BugHunter ARQ Background Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/bughunter/repo/orchestrator
EnvironmentFile=/opt/bughunter/.env
ExecStart=/usr/bin/env python3.11 -m arq worker.settings.WorkerSettings
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now bughunter-worker.service
