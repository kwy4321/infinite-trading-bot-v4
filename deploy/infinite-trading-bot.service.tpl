[Unit]
Description=Infinite Trading Bot v4 (Telegram + Toss)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=@RUN_USER@
WorkingDirectory=@INSTALL_DIR@
EnvironmentFile=@INSTALL_DIR@/.env
ExecStart=@INSTALL_DIR@/.venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
