# -*- coding: utf-8 -*-
"""
External Tools API for lpm

External tools (e.g. scripts) may access the database through this interface.
It is possible to run a filter on the items collection, get item data in JSON format, and modify items.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from datetime import datetime
from flask import Blueprint, request, current_app
from flask.ext.login import login_required, current_user
from bson.json_util import loads, dumps
from lpm.components import PartNumber
from lpm.items import create_comment, do_update_status

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
        serials = sorted([item.get('_id') for item in items])  # return a sorted list of serial numbers
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


@bp.route('/items/update/<serial>', methods=['POST'])
@login_required
def update_item(serial):
    """
    Updates the item in the database.
    Available fields:
    'set': JSON object with data to set
    'update': JSON object with data to modify. The keys must be in the
    'push': JSON object with data to push to arrays
    'status': if present, changes the status to the given string.
    'comment': if present, pushes to the comments array
    Returns the success of the operation in the JSON reply ('ok' field)
    """

    item = current_app.mongo.db.items.find_one_or_404(serial)
    ok = False
    message = ''
    now = datetime.now()

    try:
        setdata = request.form.get('set')
        updatedata = request.form.get('update')
        pushdata = request.form.get('push')
        status = request.form.get('status')
        comment = request.form.get('comment')

        partno = PartNumber(item.get('partno'))

        # data transformations
        setdata = loads(setdata) if setdata else dict()
        updatedata = loads(updatedata) if updatedata else dict()
        pushdata = loads(pushdata) if pushdata else dict()
        comments = [create_comment(comment, now)] if comment else []

        # ensure setdata does not overwrite any existing entries
        for key in setdata.keys():
            if item.get(key) is not None:
                raise ValueError("operation would overwrite existing entry '%s'" % str(key))

        # ensure updatedata contains only accepted keys
        updatemap = current_app.config['LPM_EXT_UPDATE_FIELDS']
        updatefields = updatemap.get(partno.id) or updatemap.get(partno.base_number) or \
                       updatemap.get('default') or set()
        for key in updatedata.keys():
            if not key in updatefields:
                raise ValueError("No permission to update key '%s'" % key)
        setdata.update(updatedata)

        # status handling
        if status:
            do_update_status(item, status, now=now)

        # prepare the update document
        document = {}
        if len(comments) > 0:
            pushdata['comments'] = {'$each': comments}
        if len(setdata) > 0:
            document['$set'] = setdata
        if pushdata:
            document['$push'] = pushdata

        # only perform a DB transaction if the document is not empty.
        if len(document) > 0:
            result = current_app.mongo.db.items.update_one({'_id': serial}, document)
            if result.modified_count != 1:
                raise RuntimeError('status update failed, please contact the administrator')
        ok = True

    except Exception as e:
        message = str(e)
    return _jsonify(dict(ok=ok, message=message))


def _jsonify(obj):
    return current_app.response_class(dumps(obj), mimetype='application/json')
