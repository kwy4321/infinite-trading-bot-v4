[Unit]
Description=Infinite Trading Bot Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__DEPLOY_PATH__
Environment=PATH=__DEPLOY_PATH__/.venv/bin:/usr/bin
ExecStart=__DEPLOY_PATH__/.venv/bin/streamlit run dashboard/streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
