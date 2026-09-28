"""
AssureX Extensions Module
Centralized Flask extensions instantiation to avoid circular imports.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# Configure Login Manager defaults
login_manager.login_view = "auth.login"
login_manager.login_message = "Please authenticate to access this resource."
login_manager.login_message_category = "warning"
