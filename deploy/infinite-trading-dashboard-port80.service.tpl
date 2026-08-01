[Unit]
Description=Infinite Trading Bot Streamlit Dashboard (port 80 mobile)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=__DEPLOY_PATH__
EnvironmentFile=-__DEPLOY_PATH__/.env
Environment=PATH=__DEPLOY_PATH__/.venv/bin:/usr/bin
ExecStart=__DEPLOY_PATH__/.venv/bin/streamlit run dashboard/streamlit_app.py --server.port=80 --server.address=0.0.0.0 --server.headless=true
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
