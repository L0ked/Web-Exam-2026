from flask_login import UserMixin
from werkzeug.security import check_password_hash
from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.login = user_data['login']
        self.password_hash = user_data['password_hash']
        self.first_name = user_data['first_name']
        self.last_name = user_data['last_name']
        self.middle_name = user_data['middle_name']
        self.role_id = user_data['role_id']

    @property
    def is_admin(self):
        return self.role_id == 1

    @property
    def is_moderator(self):
        return self.role_id == 2

    @property
    def is_user(self):
        return self.role_id == 3

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts)

def check_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Для выполнения данного действия необходимо пройти процедуру аутентификации", "warning")
                return redirect(url_for('auth.login', next=request.url))
            if current_user.role_id not in roles:
                flash("У вас недостаточно прав для выполнения данного действия", "danger")
                return redirect(url_for('books.index'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper
