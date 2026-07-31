[Unit]
Description=Cloudflare Tunnel for Streamlit Dashboard
After=network-online.target infinite-trading-dashboard.service
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__DEPLOY_PATH__
ExecStart=__DEPLOY_PATH__/data/cloudflared tunnel --url http://127.0.0.1:8501
Restart=on-failure
RestartSec=15
StandardOutput=append:__DEPLOY_PATH__/logs/cloudflared.log
StandardError=append:__DEPLOY_PATH__/logs/cloudflared.log

[Install]
WantedBy=multi-user.target
