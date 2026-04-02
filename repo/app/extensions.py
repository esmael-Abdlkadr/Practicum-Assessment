from flask_login import LoginManager
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
session_manager = Session()
login_manager = LoginManager()
csrf = CSRFProtect()
