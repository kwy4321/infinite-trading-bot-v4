[Unit]
Description=Infinite Trading Bot Streamlit Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__DEPLOY_PATH__
Environment=PATH=__DEPLOY_PATH__/.venv/bin:/usr/bin
ExecStart=__DEPLOY_PATH__/.venv/bin/streamlit run dashboard/streamlit_app.py --server.headless=true
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
