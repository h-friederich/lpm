# -*- coding: utf-8 -*-
"""
External Tools API for lpm

External tools (e.g. scripts) may access the database through this interface.
It is possible to run a filter on the items collection, get item data in JSON format, and modify items.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from flask import Blueprint, request, current_app
from flask.ext.login import login_required, current_user
from bson.json_util import loads, dumps

bp = Blueprint('ext', __name__)


@bp.route('/items', methods=['POST'])
@login_required
def item_filter():
    """
    Returns a list of serial numbers that fit the given filter
    Mandatory fields:
    'filter': SON object representing the filter expression
    The returned JSON object contains the following fields:
    'ok': a boolean flag denoting the success of the operation
    'message': An error message if the operation was not successful
    'serials': a list of item serial numbers matching the filter
    """
    ok = False
    message = ''
    serials = list()
    try:
        filter = request.form.get('filter')
        if not filter:
            raise ValueError('missing filter')
        filter = loads(filter)
        items = list(current_app.mongo.db.items.find(filter, projection=['_id']))
        serials = [item.get('_id') for item in items]  # return a list of serial numbers
        ok = True
    except Exception as e:
        message = str(e)
    return _jsonify(dict(ok=ok, message=message, serials=serials))


@bp.route('/items/<serial>')
@login_required
def item_info(serial):
    """
    Returns the JSON formatted object with the given serial number
    """
    obj = current_app.mongo.db.items.find_one_or_404(serial)
    return _jsonify(obj)


def _jsonify(obj):
    return current_app.response_class(dumps(obj), mimetype='application/json')
