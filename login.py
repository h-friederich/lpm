from functools import wraps
from flask import Blueprint, request, redirect, render_template, url_for, g, flash
from flask.ext.login import LoginManager, login_user, logout_user, current_user
from flask_wtf import Form
from wtforms import StringField, PasswordField
import base64
from . import auth

login_manager = LoginManager()
login_manager.login_view = 'login.login'

bp = Blueprint('login', __name__)


def init(app):
    login_manager.init_app(app)
    auth.init(app)


class LoginForm(Form):
    # Note: no input validation, submitted value will be handed in the auth module itself
    #       otherwise we'd have to fetch the full user list for every login
    username = StringField('User')
    password = PasswordField('Password')


@bp.route('/login', methods=["GET", "POST"])
def login():
    """
    Presents the login page
    If login data is POSTed, the credentials are validated and the user logged in if successful
    """
    form = LoginForm()
    if request.method == 'POST' and form.is_submitted():
        usr = auth.auth_user(form.username.data, form.password.data)
        if usr and usr.has_role('login') and usr.is_active:
            login_user(usr)
            return redirect(request.args.get('next') or url_for('items.overview'))
        elif usr is None:
            flash('invalid credentials', 'error')
        elif not usr.is_active:
            flash('login expired', 'error')
        else:
            flash('insufficient permissions', 'error')
    return render_template('login.html', form=form)


@bp.route('/logout')
def logout():
    """
    Performs a logout on the user
    """
    logout_user()
    return redirect(url_for('login.login'))


def role_required(roles):
    """
    Decorator that ensures the current user has
    - one of the specified roles (if a tuple)
    - the specified role (otherwise)
    """
    def real_role_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            introles = roles
            if not isinstance(introles, tuple):
                introles = (introles,)
            valid = False
            if current_user.is_authenticated:
                for role in introles:
                    if current_user.has_role(role):
                        valid = True
                        break

            if not valid:
                flash('insufficient privileges to access this page', 'danger')
                return login_manager.unauthorized()
            return f(*args, **kwargs)
        return wrapper
    return real_role_required


@login_manager.user_loader
def load_user(username):
    """
    Default user loader for the login plugin
    """
    return auth.get_user(username)


@login_manager.request_loader
def load_from_request(request):
    """
    User loader from basic authorization header
    (i.e. for external API)
    """
    try:
        authinfo = request.headers.get('Authorization', '').replace('Basic ', '', 1)
        username, password = base64.b64decode(authinfo).decode('utf-8').split(':')
    except:
        return None
    usr = auth.auth_user(username, password)
    if usr and usr.has_role('request_login'):
        return usr
    return None