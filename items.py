# -*- coding: utf-8 -*-
"""

Item handling module for lpm

An item consists of
- a serial number
- a part number
- a project association (optional)
- a status
- a 'available' flag (true/false)
- a list of comments

For each part number, a custom view may be defined through the LPM_ITEM_VIEW_MAP config entry.
Additional required fields for a part number may be defined through the LPM_ITEM_IMPORT_MAP config entry.

The status can contain an arbitrary string. However, the list of valid status entries can be defined in the
LPM_ITEM_STATUS_MAP config entry, where a graph of valid status transitions can be defined. In addition,
the map defines which value the 'available' flag shall have and which role is required to do the transition.

The rules of access are as follows:
- anyone may view items and add comments
- item_admin users may additionally import new items
- status changes may require a special role, depending on the LPM_ITEM_STATUS_MAP entry.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from datetime import datetime
from collections import defaultdict
from flask import Blueprint, request, current_app, flash, url_for, redirect, render_template
from flask.ext.login import login_required, current_user
from flask_wtf import Form
from wtforms import TextAreaField, StringField, SubmitField
from wtforms.validators import InputRequired
from lpm.login import role_required
from lpm.utils import extract_errors
from lpm.components import ensure_exists, PartNumber
from lpm.stock import update_batch, update_counts
from lpm.xls_files import FileForm, read_xls, save_to_tmp, extract_filepath

bp = Blueprint('items', __name__)


class CommentForm(Form):
    message = TextAreaField(label='Message', validators=[InputRequired()])


class StatusForm(Form):
    status = StringField(label='New Status', validators=[InputRequired()])
    project = StringField(label='Project')
    comment = TextAreaField(label='Comment')


class ProjectForm(Form):
    project = StringField(label='Project', validators=[InputRequired()])


@bp.route('/')
@login_required
def overview():
    """
    Shows the overview page with all items of the database
    """
    filter = {'available': True}
    if request.args.get('show_all'):
        filter = None
    objects = list(current_app.mongo.db.items.find(
            filter=filter,
            projection=['partno', 'project', 'status']
    ))
    component_records = current_app.mongo.db.components.find(projection=['name'])
    names = dict((record['_id'], record['name']) for record in component_records)
    for obj in objects:
        partno = PartNumber(obj['partno'])
        obj['_partname'] = names.get(partno.base_number, '<unknown>')
    return render_template('items/overview.html', data=objects, show_all=request.args.get('show_all'))


@bp.route('/<serial>/')
@login_required
def details(serial):
    obj = current_app.mongo.db.items.find_one_or_404(serial)
    try:
        pn = PartNumber(obj.get('partno'))
    except ValueError:
        flash('An error occurred while parsing the part number', 'error')
        return redirect(url_for('items.overview'))

    component = current_app.mongo.db.components.find_one(pn.base_number)
    if component:
        obj['_partname'] = component['name']
    else:
        obj['_partname'] = 'n/a'

    # First try the full part number, then only the base number. Use default.html as fallback
    mapping = current_app.config.get('LPM_ITEM_VIEW_MAP', dict())
    filename = mapping.get(pn.id) or mapping.get(pn.base_number) or 'default.html'
    try:
        return render_template('items/' + filename, item=obj, error=None)
    except Exception as e:
        return render_template('items/details.html', item=obj, error=str(e))


@bp.route('/<serial>/add-comment', methods=['GET', 'POST'])
@login_required
def add_comment(serial):
    current_app.mongo.db.items.find_one_or_404(serial)
    form = CommentForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        result = current_app.mongo.db.items.update_one(
                filter={'_id': serial},
                update={'$push': {'comments': _create_comment(form.message.data)}}
        )
        if result.modified_count == 1:
            flash('comment successfully added', 'success')
        else:
            flash('comment adding failed, please contact the administrator', 'error')
        return redirect(url_for('items.details', serial=serial))
    extract_errors(form)
    return render_template('items/comment_form.html', form=form, serial=serial)


@bp.route('/<serial>/change-status/<status>', methods=['GET', 'POST'])
@bp.route('/<serial>/change-status', methods=['GET', 'POST'])
@login_required
def change_status(serial, status=''):
    """
    Changes the status of the given item to the specified value
    """
    form = StatusForm(request.form)
    item = current_app.mongo.db.items.find_one_or_404(serial, projection=['partno', 'status'])

    if request.method == 'POST' and form.validate_on_submit():
        now = datetime.now()
        status = form.status.data
        project = form.project.data
        setdata = {}
        comments = []

        try:
            _check_status(item.get('partno'), item.get('status'), status)
            setdata['status'] = status
            setdata['available'] = not _is_unavailable(item.get('partno'), status)
            if project:
                setdata['project'] = project
            comments.append(_create_comment("[Auto] changed status to '%s'" % status, now))
            if form.comment.data:
                comments.append(_create_comment(form.comment.data, now))

            result = current_app.mongo.db.items.update_one(
                    filter={'_id': serial},
                    update={
                        '$set': setdata,
                        '$push': {'comments': {'$each': comments}}
                    }
            )
            if result.modified_count == 1:
                flash('status successfully updated', 'success')
            else:
                flash('status update failed, please contact the administrator', 'error')
            return redirect(url_for('items.details', serial=serial))

        except Exception as e:
            flash(e, 'error')

    extract_errors(form)
    if status is not None:
        form.status.data=status
    return render_template('items/status_form.html', serial=serial, item=item, form=form)


@bp.route('/<serial>/set-project', methods=['GET', 'POST'])
@login_required
def set_project(serial):
    """
    Changes the project association of the given item to the specified value
    """
    form = ProjectForm(request.form)
    current_app.mongo.db.items.find_one_or_404(serial)

    if request.method == 'POST' and form.validate_on_submit():
        project = form.project.data
        comment = _create_comment("[Auto] changed project association to '%s'" % project)
        result = current_app.mongo.db.items.update_one(
                filter={'_id': serial},
                update={
                    '$set': {'project': project},
                    '$push': {'comments': comment}
                }
        )
        if result.modified_count == 1:
            flash('project successfully set', 'success')
        else:
            flash('failed to set the project, please contact the administrator', 'error')
        return redirect(url_for('items.details', serial=serial))
    extract_errors(form)
    return render_template('items/project_form.html', form=form, serial=serial)


@bp.route('/import', methods=['GET', 'POST'])
@role_required('item_admin')
def import_items():
    form = FileForm(request.form)
    # WTF is NOT used for the file handling, since the file upload handling seems broken.
    if request.method == 'POST' and form.validate_on_submit():
        # show the validation page if a file is uploaded
        # else process the tmpname parameter
        if request.files.get('file'):  # a file was uploaded
            try:
                save_to_tmp(form)
                success, headers, values = _import_file(extract_filepath(form))
                return render_template('items/validate_form.html',
                                       title='Verify Item Data',
                                       form=form,
                                       headers=headers,
                                       data=values)
            except Exception as e:
                flash(e, 'error')

        elif form.tmpname.data:
            # re-run the data import and insert items into the database
            success, headers, values = _import_file(extract_filepath(form))
            if success:
                try:
                    _store_items(values)
                    flash('item import successful', 'success')
                    return redirect(url_for('items.overview'))
                except Exception as e:
                    flash(e, 'error')
            return render_template('items/validate_form.html',
                                   title='Verify Item Data',
                                   form=form,
                                   headers=headers,
                                   data=values)

    extract_errors(form)
    return render_template('items/import_form.html', title='Import Items File', form=form)


def get_requirements(partno):
    reqs = current_app.config['LPM_ITEM_IMPORT_MAP']
    return reqs.get(partno.id) or reqs.get(partno.base_number) or dict()


def process_requirements(obj, reqs):
    required_fields = reqs.get('required_fields', list())
    date_fields = reqs.get('date_fields', list())
    integer_fields = reqs.get('integer_fields', list())
    floating_point_fields = reqs.get('floating_point_fields', list())
    boolean_fields = reqs.get('boolean_fields', list())

    for key in required_fields:
        if key not in obj:
            raise ValueError("required field '%s' is missing" % key)

    for key, value in obj.items():
        if key in date_fields:
            if not isinstance(value, datetime):
                raise ValueError("field '%s' must be a datetime object" % key)
        elif key in integer_fields:
            obj[key] = int(value)
        elif key in floating_point_fields:
            obj[key] = float(value)
        elif key in boolean_fields:
            value = str(value)
            if value == '0' or value.lower() == 'false' or value.lower() == 'no':
                obj[key] = False
            elif value == '1' or value.lower() == 'true' or value.lower() == 'yes':
                obj[key] = True
            else:
                raise ValueError("cannot parse field '%s' as a boolean" % key)
        else:
            obj[key] = str(obj[key])

    # need to check the status transition validity
    if 'status' in obj:
        _check_status(obj.get('partno'), '', obj.get('status'))


def _import_file(filepath):
    """
    Processes the XLS data, ensures that the part numbers exist (incl. revision)
    and that all the required fields are set.
    If something is missing a warning is flashed but processing continues.
    Returns a tuple (success, headers, data)
    """
    headers, data = read_xls(filepath)
    success = True
    if 'partno' not in headers:
        raise ValueError("'partno' column is missing")
    if 'serial' not in headers:
        raise ValueError("'serial' column is missing")
    if '_id' in headers:
        raise ValueError("reserved column name: '_id'")
    if 'comments' in headers:
        raise ValueError("reserved column name: 'comments'")
    if 'available' in headers:
        raise ValueError("reserved column name: 'available'")
    for idx, item in enumerate(data):
        try:
            pn = PartNumber(item.get('partno'))
            ensure_exists(pn.base_number)
            if pn.revision is None:
                raise ValueError('part number requires a revision')
            serial = item.get('serial')
            if not serial:
                raise ValueError('serial number is missing')
            # transform the serial to a string AFTER checking it exists. Otherwise the string would read 'None'
            serial = str(serial)
            if current_app.mongo.db.items.find_one(serial):
                raise ValueError("serial number '%s' exists already" % serial)

            reqs = get_requirements(pn)
            process_requirements(item, reqs)
        except Exception as e:
            flash('%s (row %d)' % (e, (idx+2)), 'error')
            success = False
    return success, headers, data


def _store_items(data):
    """
    Saves the provided items in the database.
    Applied transformations:
    The 'serial' key is transformed to the '_id' key
    A 'comment' key is pushed to the comments array
    """
    quantities = defaultdict(int)  # for the stock update
    now = datetime.now()
    for idx, item in enumerate(data):
        assert 'serial' in item
        assert 'partno' in item
        item['_id'] = item.pop('serial')
        if 'project' not in item:
            item['project'] = ''
        if 'status' in item:
            item['available'] = not _is_unavailable(item['partno'], item['status'])
        else:
            item['status'] = ''
            item['available'] = True
        comments = [_create_comment('[Auto] created', now)]
        comment = item.pop('comment', None)
        if comment:
            comments.append(_create_comment(comment, now))
        item['comments'] = comments
        current_app.mongo.db.items.insert(item)

        # count the number of occurrences per model number
        partno = PartNumber(item.get('partno'))
        quantities[partno.base_number] += 1

        # update the batch information if present
        batch = item.get('batch')
        if batch:
            update_batch(partno.base_number, batch, 1)

    # add the items to the stock as well
    for partno, value in quantities.items():
        update_counts(partno, value, None, 'items added')


def _create_comment(comment, date=None):
    """
    Creates a comment object
    """
    if date is None:
        date = datetime.now()
    return {'user': current_user.id, 'date': date, 'message': comment}


def _check_status(partno, current_status, new_status):
    pn = PartNumber(partno)
    partmap = current_app.config.get('LPM_ITEM_STATUS_MAP', dict())
    map = partmap.get(pn.id) or partmap.get(pn.base_number) or partmap.get('default') or dict()
    if new_status not in map:
        raise ValueError("unknown status: '%s'" % new_status)
    definition = map.get(new_status)
    origins = definition.get('origins')
    if current_status not in origins:
        raise ValueError("Invalid status transition: from '%s' to '%s'" % (current_status, new_status))
    role = definition.get('role')
    if role and not current_user.has_role(role):
        raise ValueError("insufficient permissions to do the status transition from '%s' to '%s'"
                         % (current_status, new_status))


def _is_unavailable(partno, status):
    pn = PartNumber(partno)
    partmap = current_app.config.get('LPM_ITEM_STATUS_MAP', dict())
    map = partmap.get(pn.id) or partmap.get(pn.base_number) or partmap.get('default') or dict()
    definition = map.get(status)
    return definition.get('unavailable', False)
