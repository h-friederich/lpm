# -*- coding: utf-8 -*-
"""
Simple config-based authentication module for lpm

Encapsulates a user, compatible with flask-login and provides a has_role() method.
This is considered simpler to use than e.g. flask-principal

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from flask import current_app
from . import _User


def auth_user(username, password):
    users = current_app.config['LPM_AUTH_USERS']
    if username in users:
        data = users[username]
        if password == data['password']:
            return _User(id=username, name=data['name'], roles=data['roles'], active=data['active'])
    return None


def get_user(username):
    users = current_app.config['LPM_AUTH_USERS']
    if username in users:
        data = users[username]
        return _User(id=username, name=data['name'], roles=data['roles'], active=data['active'])
    return None


def get_active_users():
    users = current_app.config['LPM_AUTH_USERS']
    # remove inactive users
    return sorted([_User(id=username, name=data['name'], roles=data['roles'], active=data['active'])
                   for username,data in users.items() if data['active'] ])
