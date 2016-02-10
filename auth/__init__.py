# -*- coding: utf-8 -*-
"""
Authentication module for lpm

Encapsulates a user, compatible with flask-login and provides a has_role() method.
This is considered simpler to use than e.g. flask-principal

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from flask import current_app


def init(app):
    src = app.config['LPM_AUTH_SRC']
    if src == 'simple':
        from . import simple
        app.auth = simple
    else:
        raise ValueError('Unknown backend')


def auth_user(username, password):
    """
    Attempts to authenticate the given username with password.
    :param username: The username with which to authenticate.
    :param password: The password with which to authenticate.
    :return: a flask-login compatible user object upon successful authentication, else None.
    """
    return current_app.auth.auth_user(username, password)


def get_user(username):
    """
    Returns the user object associated with this username
    :param username: The username to look up
    :return: a flask-login compatible user object if username exists, else None.
    """
    return current_app.auth.get_user(username)


def get_users_with_role(role):
    """
    Returns all users that have the given role
    :param role:
    :return: A list of users which have the given role
    """
    users = current_app.auth.get_active_users()
    return [u for u in users if u.has_role(role)]


class _User:
    """
    flask-login compatible user class
    """

    def __init__(self, id, name, roles, active):
        self._id = id
        self._name = name
        self._roles = roles
        self._active = active

    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self._active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return self._id

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    def has_role(self, role):
        return role in self._roles

    def __lt__(self, other):
        return self.id < other.id

    def __le__(self, other):
        return not (self > other)

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not (self == other)

    def __gt__(self, other):
        return self.id > other.id

    def __ge__(self, other):
        return not (self < other)

    def __repr__(self):
        return self.name
