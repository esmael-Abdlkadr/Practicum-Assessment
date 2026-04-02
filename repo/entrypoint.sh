#!/bin/bash
set -e

mkdir -p /app/data
mkdir -p /app/flask_session

python -c "from app import create_app; from app.extensions import db; app = create_app(); app.app_context().push(); db.create_all()"
python -m app.seed

flask run --host=0.0.0.0 --port=5000
