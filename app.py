from flask import Flask, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
import os
from db import get_db_connection

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'defaultsecret')
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'covers')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "Для выполнения данного действия необходимо пройти процедуру аутентификации"
login_manager.login_message_category = "warning"

from auth import User

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(user_data)
    return None

@app.errorhandler(403)
def forbidden(error):
    flash("У вас недостаточно прав для выполнения данного действия", "danger")
    return redirect(url_for('books.index'))

from auth import auth_bp
from books import books_bp
from reviews import reviews_bp

app.register_blueprint(auth_bp)
app.register_blueprint(books_bp)
app.register_blueprint(reviews_bp)

if __name__ == '__main__':
    app.run(debug=True)
