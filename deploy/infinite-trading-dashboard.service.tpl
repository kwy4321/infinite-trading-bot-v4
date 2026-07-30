[Unit]
Description=Infinite Trading Bot Streamlit Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__DEPLOY_PATH__
EnvironmentFile=__DEPLOY_PATH__/.env
Environment=PATH=__DEPLOY_PATH__/.venv/bin:/usr/bin
ExecStart=__DEPLOY_PATH__/.venv/bin/streamlit run dashboard/streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
