[Unit]
Description=Cloudflare Tunnel for Streamlit Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__DEPLOY_PATH__
ExecStartPre=/bin/bash -c 'for i in $(seq 1 30); do curl -sf -o /dev/null --max-time 3 http://127.0.0.1:8501 && exit 0; sleep 2; done; exit 0'
ExecStart=__DEPLOY_PATH__/data/cloudflared tunnel --loglevel info --no-autoupdate --url http://127.0.0.1:8501
Restart=always
RestartSec=10
StartLimitIntervalSec=0
StandardOutput=append:__DEPLOY_PATH__/logs/cloudflared.log
StandardError=append:__DEPLOY_PATH__/logs/cloudflared.log

[Install]
WantedBy=multi-user.target
