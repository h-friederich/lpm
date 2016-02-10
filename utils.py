from flask import flash, g
from bson.json_util import dumps
from . import auth


def extract_errors(form):
    """
    Extracts errors from the form and flashes them
    """
    for key, msgs in form.errors.items():
        for msg in msgs:
            flash(key + ': ' + msg, 'error')


def init(app):
    """
    Registers useful template filters at the passed app
    """

    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        """
        datetime formatter for ISO8601-like dates
        """
        return value.strftime(format)

    @app.template_filter('fullname')
    def fullname(short):
        """
        Returns the full name for the given user ID
        """
        if not short:
            return 'n/a'
        if not 'usernames' in g:
            g.usernames = dict()
        usernames = g.usernames

        if not short in usernames:
            user = auth.get_user(short)
            if not user:
                usernames[short] = short
            else:
                usernames[short] = user.name
        return usernames[short]

    @app.template_filter('tojson')
    def tojson(obj, indent=2):
        """
        overrides the default Flask tojson filter to use the BSON-aware implementation
        """
        return dumps(obj, indent=indent)
