[Unit]
Description=Infinite Trading Bot v4 (Telegram + Toss)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=@RUN_USER@
WorkingDirectory=@INSTALL_DIR@
EnvironmentFile=@INSTALL_DIR@/.env
ExecStartPre=/bin/bash -c 'cd @INSTALL_DIR@ && bash scripts/kill_all_bots.sh || true'
ExecStart=@INSTALL_DIR@/.venv/bin/python main.py
Restart=on-failure
RestartSec=15
KillMode=mixed
TimeoutStopSec=20
# GCP e2-micro (1GB RAM) — OOM 방지
MemoryHigh=380M
MemoryMax=450M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
