# -*- coding: utf-8 -*-
"""
Stock handling module for lpm

All stock entries are connected to a revisionless part number. The revision number is not considered since
lpm considers revisions to be compatible and thus interchangeable.

The database stores the current count and optionally a BOM for a component.
When the count is updated the BOM rules are considered and the counts of child parts updated accordingly.

The rules of access are as follows:
- anyone may view the stock
- stock_admin users may additionally:
  - add new items to the stock
  - correct the stock numbers
  - set the BOM rules

Note: There count is not validated, i.e. may become negative.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from datetime import datetime
from flask import Blueprint, current_app, request, redirect, render_template, url_for, flash
from flask.ext.login import login_required, current_user
from flask_wtf import Form
from wtforms import IntegerField, StringField
from wtforms.validators import InputRequired
from lpm.login import role_required
from lpm.utils import extract_errors
from lpm.components import ensure_exists
from lpm.xls_files import FileForm, read_xls, save_to_tmp, extract_filepath

bp = Blueprint('stock', __name__)


class AddSingleForm(Form):
    quantity = IntegerField(label='Added Quantity', validators=[InputRequired()])
    batch = StringField(label='Batch Name')


class CorrectSingleForm(Form):
    quantity = IntegerField(label='New Quantity', validators=[InputRequired()])
    comment = StringField(label='Comment')


@bp.route('/')
@login_required
def overview():
    """
    Shows the overview page containing all components
    """
    objects = list(current_app.mongo.db.stock.find())
    component_records = current_app.mongo.db.components.find(projection=['name'])
    names = dict((record['_id'], record['name']) for record in component_records)
    for obj in objects:
        obj['name'] = names.get(obj['_id'])
    return render_template('stock/overview.html', data=objects)


@bp.route('/<partno>')
@login_required
def details(partno):
    obj = current_app.mongo.db.stock.find_one_or_404(partno)
    component_records = current_app.mongo.db.components.find(projection=['name'])
    names = dict((record['_id'], record['name']) for record in component_records)
    obj['name'] = names[partno]
    obj['history'] = list(current_app.mongo.db.stock_history.find({'partno': partno}))
    for entry in obj.get('bom', list()):
        entry['name'] = names.get(entry.get('partno'))
    batches = list(current_app.mongo.db.stock_batches.find({'partno': partno}))
    return render_template('stock/details.html', data=obj, batches=batches)


@bp.route('/add', methods=['GET', 'POST'])
@role_required('stock_admin')
def add():
    """
    Imports data from the uploaded file and updates the stock values including BOM results
    """
    form = FileForm(request.form)
    # WTF is NOT used for the file handling, since the file upload handling seems broken.
    if request.method == 'POST' and form.validate_on_submit():
        # show the validation page if a file is uploaded
        # else process the tmpname parameter
        if request.files.get('file'):
            try:
                save_to_tmp(form)
                success, headers, values = _import_file(extract_filepath(form))
                # Also add the current quantity to the review list
                for item in values:
                    current_quantity = 0
                    obj = current_app.mongo.db.stock.find_one(item.get('partno'))
                    if obj:
                        current_quantity = obj.get('quantity')
                    item['current_quantity'] = current_quantity
                    item['new_quantity'] = item.get('quantity') + current_quantity
                headers.append('current_quantity')
                headers.append('new_quantity')
                return render_template('stock/validate_form.html',
                                       form=form,
                                       headers=headers,
                                       data=values,
                                       title='Verify Input Data',
                                       action='Add to Stock')
            except Exception as e:
                flash(e, 'error')

        elif form.tmpname.data:
            success, headers, values = _import_file(extract_filepath(form))
            if success:
                try:
                    for v in values:
                        partno = v.get('partno')
                        quantity = v.get('quantity')
                        batchname = v.get('batch')
                        comment = v.get('comment', 'added to stock')
                        update_counts(partno, quantity, batchname, comment)
                    flash('stock import successful', 'success')
                    return redirect(url_for('stock.overview'))
                except Exception as e:
                    flash(e, 'error')
            return render_template('stock/validate_form.html',
                                   form=form,
                                   headers=headers,
                                   data=values,
                                   title='Verify Input Data',
                                   action='Add to Stock')
    extract_errors(form)
    return render_template('stock/import_form.html', form=form, title='Add Stock Items')


@bp.route('/correct', methods=['GET', 'POST'])
@role_required('stock_admin')
def correct():
    """
    Imports data from the uploaded file and corrects the corresponding stock values
    """
    form = FileForm(request.form)
    warning = dict(category='warning',
                   message='You are about to override the exising stock! Are you sure you want to continue?')
    # WTF is NOT used for the file handling, since the file upload handling seems broken.
    if request.method == 'POST' and form.validate_on_submit():
        # show the validation page if a file is uploaded
        # else process the tmpname parameter
        if request.files.get('file'):
            try:
                save_to_tmp(form)
                success, headers, values = _import_file(extract_filepath(form))
                for item in values:
                    current_quantity = 0
                    obj = current_app.mongo.db.stock.find_one(item.get('partno'))
                    if obj:
                        current_quantity = obj.get('quantity')
                    item['current_quantity'] = current_quantity
                headers.append('current_quantity')
                return render_template('stock/validate_form.html',
                                       form=form,
                                       headers=headers,
                                       data=values,
                                       title='Verify Correction Data',
                                       action='Apply Correction',
                                       warning=warning)
            except Exception as e:
                flash(e, 'error')

        elif form.tmpname.data:
            success, headers, values = _import_file(extract_filepath(form))
            if success:
                try:
                    for v in values:
                        partno = v.get('partno')
                        quantity = v.get('quantity')
                        comment = v.get('comment', 'manual correction')
                        correct_counts(partno, quantity, comment)
                    flash('stock correction successful', 'success')
                    return redirect(url_for('stock.overview'))
                except Exception as e:
                    flash(e, 'error')
            return render_template('stock/validate_form.html',
                                   form=form,
                                   headers=headers,
                                   data=values,
                                   title='Verify Correction Data',
                                   action='Apply Correction',
                                   warning=warning)
    extract_errors(form)
    return render_template('stock/import_form.html', form=form, title='Correct Stock Items', warning=warning)


@bp.route('/update-bom', methods=['GET', 'POST'])
@role_required('stock_admin')
def update_bom():
    """
    Imports data from the uploaded file and corrects the corresponding stock values
    """
    form = FileForm(request.form)
    # WTF is NOT used for the file handling, since the file upload handling seems broken.
    if request.method == 'POST' and form.validate_on_submit():
        # show the validation page if a file is uploaded
        # else process the tmpname parameter
        if request.files.get('file'):  # a file was uploaded
            try:
                save_to_tmp(form)
                success, headers, values = _import_file(extract_filepath(form))
                target_partno = 'unknown'
                if len(values) > 0:
                    target_partno = values.pop(0).get('partno')
                return render_template('stock/validate_form.html',
                                       form=form,
                                       headers=headers,
                                       data=values,
                                       title='Verify BOM Data for '+target_partno,
                                       action='Update BOM')
            except Exception as e:
                flash(e, 'error')

        elif form.tmpname.data:
            success, headers, values = _import_file(extract_filepath(form))
            target_partno = 'unknown'
            if len(values) > 0:
                target_partno = values.pop(0).get('partno')
            if success:
                try:
                    set_bom(target_partno, values)
                    flash('BOM update successful', 'success')
                    return redirect(url_for('stock.overview'))
                except Exception as e:
                    flash(e, 'error')
            return render_template('stock/validate_form.html',
                                   form=form,
                                   headers=headers,
                                   data=values,
                                   title='Verify BOM Data for '+target_partno,
                                   action='Update BOM')
    extract_errors(form)
    return render_template('stock/import_form.html', form=form, title='Update BOM')

@bp.route('/<partno>/add-single', methods=['GET', 'POST'])
@role_required('stock_admin')
def add_single(partno):
    """
    Adds the given quantity to the stock
    """
    obj = current_app.mongo.db.components.find_one_or_404(partno, projection=['name'])
    form = AddSingleForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            update_counts(partno, form.quantity.data, form.batch.data, 'added to stock')
            flash('Stock addition successful', 'success')
            return redirect(url_for('stock.details', partno=partno))
        except Exception as e:
            flash('stock operation failed (%s), please contact the administrator' % e, 'error')
    extract_errors(form)
    name = obj.get('name')
    return render_template('stock/add_single.html', form=form, partno=partno, name=name)


@bp.route('/<partno>/correct-single', methods=['GET', 'POST'])
@role_required('stock_admin')
def correct_single(partno):
    """
    Corrects the stock and sets the new quantity
    """
    component = current_app.mongo.db.components.find_one_or_404(partno, projection=['name'])
    form = CorrectSingleForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            message = 'stock correction'
            if form.comment.data:
                message += ' (%s)' % form.comment.data
            correct_counts(partno, form.quantity.data, message)
            flash('Stock correction successful', 'success')
            return redirect(url_for('stock.details', partno=partno))
        except Exception as e:
            flash('stock operation failed (%s), please contact the administrator' % e, 'error')
    extract_errors(form)
    name = component.get('name')
    obj = current_app.mongo.db.stock.find_one(partno)
    current_quantity = obj.get('quantity') if obj is not None else 0
    return render_template('stock/correct_single.html',
                           form=form, partno=partno, name=name,
                           current_quantity=current_quantity)


def update_counts(partno, quantity, batchname, message):
    """
    Updates the given stock entry, creating it if necessary.
    Raises an exception if the part number is not valid or if there is a database problem
    """
    _check_bom(partno)  # validation
    _do_update_counts(partno, quantity, batchname, message)


def correct_counts(partno, quantity, message):
    result = current_app.mongo.db.stock.update_one(
            filter={'_id': partno},
            update={'$set': {'quantity': quantity}},
            upsert=True,
    )
    if result.modified_count == 0 and result.upserted_id is None:
        raise RuntimeError('no stock database object modified nor created')
    result = current_app.mongo.db.stock_history.insert_one({
        'date': datetime.now(),
        'partno': partno,
        'quantity': quantity,
        'message': message
    })
    if result.inserted_id is None:
        raise RuntimeError('no stock history object created')


def update_batch(partno, batchname, quantity):
    """
    Updates the given stock batch item, creating it if necessary.
    Raises an exception if the part number is not valid or if there is a database problem
    """
    if quantity < 0:
        raise ValueError('A batch cannot have negative quantities')
    ensure_exists(partno)
    if quantity == 0 or not batchname:
        return  # nothing to do
    result = current_app.mongo.db.stock_batches.update_one(
            filter={
                'partno': partno,
                'name': batchname
            },
            update={'$inc': {'quantity': quantity}},
            upsert=True
    )
    if result.modified_count == 0 and result.upserted_id is None:
        raise RuntimeError('no stock batch object modified nor created')


def set_bom(partno, data):
    """
    Updates the BOM data for the given part number
    """
    ensure_exists(partno)
    bomdata = list()
    for item in data:
        p = item.get('partno')
        ensure_exists(p)
        bomdata.append(dict(partno=p, quantity=int(item['quantity'])))
    result = current_app.mongo.db.stock.update_one(
            filter={'_id': partno},
            update={'$set': {'bom': bomdata}},
            upsert=True)
    if result.modified_count == 0 and result.upserted_id is None:
        raise RuntimeError('no BOM object modified nor created')


def _do_update_counts(partno, quantity, batchname, message):
    if quantity == 0:
        return  # nothing to do

    # update the current component including batch and history before following the BOM rules.
    # in case there is a database problem the highest-level stock entry will most likely be correct.
    result = current_app.mongo.db.stock.update_one(
            filter={'_id': partno},
            update={'$inc': {'quantity': quantity}},
            upsert=True
    )
    if result.modified_count == 0 and result.upserted_id is None:
        raise RuntimeError('database update problem: %s' % str(result))
    if quantity > 0:
        update_batch(partno, batchname, quantity)
    result = current_app.mongo.db.stock_history.insert_one({
        'date': datetime.now(),
        'partno': partno,
        'delta': quantity,
        'message': message
    })
    if result.inserted_id is None:
        raise RuntimeError('no stock history object created')

    # only run the BOM rules if something is added to the stock
    if quantity <= 0:
        return
    bom = current_app.mongo.db.stock.find_one(partno).get('bom', list())
    for item in bom:
        _do_update_counts(item.get('partno'), quantity*item.get('quantity')*-1, None, '(BOM rule)')


def _check_bom(partno, tree=set()):
    """
    Recursively checks that the BOM tree is valid.
    The tree parameter tracks the parents of the current node, use an empty set for the top-level component
    """
    ensure_exists(partno)

    # obtain the BOM
    obj = current_app.mongo.db.stock.find_one(partno)
    if not obj:
        return
    bom = obj.get('bom', list())
    if len(bom) == 0:
        return

    # recursively check the BOM
    tree.add(partno)
    for entry in bom:
        pn = entry.get('partno')
        if pn in tree:
            raise RuntimeError('Infinite loop detected')
        _check_bom(pn, tree)
    tree.remove(partno)


def _import_file(filepath):
    headers, data = read_xls(filepath)
    success = True
    if 'quantity' not in headers:
        raise ValueError("'quantity' column is missing")
    if 'partno' not in headers:
        raise ValueError("'partno' column is missing")
    for idx, item in enumerate(data):
        try:
            # the part number must exist
            # quantity is optional, set as zero if missing
            ensure_exists(item.get('partno'))
            qstr = item.get('quantity')
            if qstr:
                quantity = int(qstr)
            else:
                quantity = 0
            if quantity < 0:
                raise ValueError('quantity must be non-negative')
            item['quantity'] = quantity
        except Exception as e:
            flash('%s (row %d)' % (e, (idx+2)), 'error')
            success = False
    return success, headers, data