# -*- coding: utf-8 -*-
"""
Debug module for lpm

This module allows to modify the raw database document in JSON format.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from flask import Blueprint, current_app, request, flash, render_template, abort
from flask.ext.pymongo import ObjectId
from flask_wtf import Form
from wtforms import TextAreaField, SubmitField
from wtforms.validators import InputRequired
from bson.json_util import dumps, loads
from lpm.login import role_required
from lpm.utils import extract_errors

bp = Blueprint('debug', __name__)


class DebugForm(Form):
    # TODO: JSON validator?
    document = TextAreaField(label='Document', validators=[InputRequired()])


@bp.route('/<collection>/<id>', methods=['GET', 'POST'])
@role_required('db_debug')
def debug(collection, id):
    try:
        obj = current_app.mongo.db[collection].find_one(id)
        if obj is None:
            try:
                id = ObjectId(id)
                obj = current_app.mongo.db[collection].find_one_or_404(id)
            except:
                abort(404)
        obj = dumps(obj, indent=2)  # transform to pretty JSON
        form = DebugForm(request.form, data=dict(document=obj))
        if request.method == 'POST' and form.validate_on_submit():
            try:
                new_obj = loads(form.document.data)
                result = current_app.mongo.db[collection].find_one_and_replace(
                        filter={'_id': id},
                        replacement=new_obj
                )
                if result:
                    flash('data successfully updated', 'success')
                    obj = current_app.mongo.db[collection].find_one_or_404(id)
                    form.document.data = dumps(obj, indent=2)
                else:
                    flash('data update failed', 'error')
            except Exception as e:
                flash(e, 'error')
        # show the form page
        extract_errors(form)

        return render_template('debug/debug_form.html', collection=collection, id=id, form=form, obj=obj)
    except Exception as e:
        return str(e)  # always return something meaningful
