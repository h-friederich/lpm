# -*- coding: utf-8 -*-
"""
Component management module for lpm

A component definition consists of (at least):
- an ID (part number)
- a descriptive name
- a description
- a category
- a list of suppliers
- a list of manufacturers
- a list of revisions consisting of:
    - a description
    - a list of files
- a 'released' flag
- an 'obsolete' flag
- a history

Additional data may be specified as standard Python dictionary entries.

The latest revision is always the active one while earlier revisions are kept for archiving purposes.
Once a component is released it is immutable. Only admins can change the released flag or mark a component as obsolete.

The rules of access are as follows:
- anyone may view component definitions
- component_edit users may additionally:
    - create new components
    - modify components that are not currently released.
    - create a new revision for components that are released.
- component_admin users may additionally:
    - release / un-release components
    - obsolete components

Valid categories can be defined with the LPM_COMPONENT_CATEGORIES configuration entry.

Note: There is no lock mechanism available, i.e. multiple users may edit the same component simultaneously.

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

import re
import os
from datetime import datetime
from werkzeug import secure_filename
from flask import Blueprint, current_app, render_template, flash, abort, redirect, url_for, request, send_from_directory
from flask.ext.login import login_required, current_user
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from flask_wtf import Form
from wtforms import TextAreaField, StringField, SubmitField, FileField, SelectField
from wtforms.validators import InputRequired
from lpm.login import role_required
from lpm.utils import extract_errors

bp = Blueprint('components', __name__)


class ComponentForm(Form):
    name = StringField(label='Name', validators=[InputRequired()])
    description = TextAreaField(label='Description')
    category = SelectField(label='Category', validators=[InputRequired()])
    comment = TextAreaField(label='Revision Comment')
    supplier1 = StringField(label='Supplier 1')
    supplier1part = StringField('Supplier 1 Part Number')
    supplier2 = StringField(label='Supplier 2')
    supplier2part = StringField('Supplier 2 Part Number')
    manufacturer1 = StringField(label='Manufacturer 1')
    manufacturer1part = StringField('Manufacturer 1 Part Number')
    manufacturer2 = StringField(label='Manufacturer 2')
    manufacturer2part = StringField('Manufacturer 2 Part Number')


class UploadForm(Form):
    file = FileField(label='File')


class RevisionForm(Form):
    comment = TextAreaField(label='Revision Comment')


class ReleaseForm(Form):
    action = SubmitField(label='Release')


class UnReleaseForm(Form):
    action = SubmitField(label='Un-Release')


class ObsoleteForm(Form):
    action = SubmitField(label='Mark as Obsolete')


@bp.route('/')
@login_required
def overview():
    """
    Shows the overview page containing all components
    """
    filter = {'obsolete': False}
    if request.args.get('show_obsolete'):
        filter = None
    data = current_app.mongo.db.components.find(filter=filter, projection=['name', 'category', 'obsolete', 'released'])
    return render_template('components/overview.html', data=data,
                           show_obsolete=request.args.get('show_obsolete'))


@bp.route('/<partno>')
@login_required
def details(partno):
    """
    Shows the details about the given component
    - Only component_edit users may look at specific revisions
    - All other only see the latest revision
    """
    try:
        pn = PartNumber(partno)
    except ValueError:
        abort(404)

    # redirect to the revisionless URL if the user cannot view outdated revisions
    if pn.revision is not None and not current_user.has_role('component_edit'):
        return redirect(url_for('components.details', partno=pn.base_number))

    # ensure the object exists and the revision is valid
    obj = current_app.mongo.db.components.find_one_or_404(pn.base_number)

    # ensure the desired revision exists
    num_revisions = len(obj.get('revisions', list()))
    if pn.revision_number is not None and pn.revision_number >= num_revisions:
        abort(404)
    pn.set_num_revisions(num_revisions)

    files = _get_files(pn.id)

    preview_file = None
    for file in files:
        if file.startswith('preview.'):
            preview_file = file
            break

    return render_template('components/details.html', data=obj,
                           partno=pn, files=files, preview_file=preview_file)


@bp.route('/<partno>/<file>')
@login_required
def file(partno, file):
    """
    Sends the specified file, after performing some access checks.

    Only component_edit users may look at all revisions, all other may only see the latest revision
    """
    try:
        pn = PartNumber(partno)
    except ValueError:
        abort(404)

    # a revision must be specified
    if pn.revision is None:
        abort(404)

    # ensure the object exists and the revision is valid
    obj = current_app.mongo.db.components.find_one_or_404(pn.base_number)

    # ensure the desired revision exists
    num_revisions = len(obj.get('revisions', list()))
    assert pn.revision_number is not None
    if pn.revision_number >= num_revisions:
        abort(404)
    pn.set_num_revisions(num_revisions)

    if pn.is_outdated() and not current_user.has_role('component_edit'):
        abort(403)

    # instruct werkzeug to stream the file
    dir = os.path.join(current_app.config['LPM_COMPONENT_FILES_DIR'], partno)
    return send_from_directory(dir, file)


@bp.route('/add', methods=['GET', 'POST'])
@role_required('component_edit')
def add():
    """
    Presents the form to add a new component, and adds it to the database if submitted
    """
    form = ComponentForm(request.form)
    form.category.choices = _get_categories()
    # form submittal handling
    if request.method == 'POST' and form.validate_on_submit():
        id = _create_new_partno()
        suppliers = _extract_suppliers(form)
        manufacturers = _extract_manufacturers(form)
        now = datetime.now()
        obj = dict(_id=id,
                   name=form.name.data,
                   description=form.description.data,
                   category=form.category.data,
                   suppliers=suppliers,
                   manufacturers=manufacturers,
                   revisions=[{'date': now, 'comment': form.comment.data}],
                   released=False,
                   obsolete=False,
                   history=[{'date': now, 'user': current_user.id, 'message': 'created'}])
        try:
            current_app.mongo.db.components.insert(obj)
            flash('component successfully created', 'success')
            return redirect(url_for('components.details', partno=id))
        except DuplicateKeyError as e:
            flash('data insertion failed (%s), please contact the administrator' % e, 'error')
    extract_errors(form)
    return render_template('components/new_form.html', form=form, type=type)


@bp.route('/<partno>/edit', methods=['GET', 'POST'])
@role_required('component_edit')
def edit(partno):
    """
    Presents the form to edit an already existing component
    """
    obj = _load_if_unreleased(partno)

    # prepare the form data
    revisions = obj.get('revisions')
    suppliers = obj.get('suppliers', list())
    manufacturers = obj.get('manufacturers', list())
    revidx = len(revisions)-1
    num_suppliers = len(suppliers)
    num_manufacturers = len(manufacturers)
    data = dict(name=obj.get('name'),
                description=obj.get('description'),
                category=obj.get('category'),
                comment=revisions[revidx].get('comment'))
    if num_suppliers > 0:
        data['supplier1'] = suppliers[0].get('name')
        data['supplier1part'] = suppliers[0].get('partno')
    if num_suppliers > 1:
        data['supplier2'] = suppliers[1].get('name')
        data['supplier2part'] = suppliers[1].get('partno')
    if num_manufacturers > 0:
        data['manufacturer1'] = manufacturers[0].get('name')
        data['manufacturer1part'] = manufacturers[0].get('partno')
    if num_manufacturers > 1:
        data['manufacturer2'] = manufacturers[1].get('name')
        data['manufacturer2part'] = manufacturers[1].get('partno')
    form = ComponentForm(request.form, data=data)
    form.category.choices = _get_categories()

    # form submittal handling
    # use $set for the updated fields, directly update the latest revision
    # add a comment in the history
    if request.method == 'POST' and form.validate_on_submit():
        suppliers = _extract_suppliers(form)
        manufacturers = _extract_manufacturers(form)
        set_data = dict(name=form.name.data,
                        description=form.description.data,
                        category=form.category.data,
                        suppliers=suppliers,
                        manufacturers=manufacturers)
        set_data['revisions.'+str(revidx)+'.comment'] = form.comment.data
        result = current_app.mongo.db.components.update_one(
                filter={'_id': partno},
                update={
                    '$set': set_data,
                    '$push': {
                        'history': {
                            'date': datetime.now(),
                            'user': current_user.id,
                            'message': 'updated',
                        }
                    }
                }
        )
        if result.modified_count == 1:
            flash('data successfully updated', 'success')
        else:
            # should not happen. If the ID is wrong, the initial lookup will fail
            flash('no data modified, please contact the administrator', 'error')
        return redirect(url_for('components.details', partno=partno))
    extract_errors(form)
    return render_template('components/edit_form.html', form=form, partno=partno)


@bp.route('/<partno>/fileupload', methods=['GET', 'POST'])
@role_required('component_edit')
def fileupload(partno):
    """
    Presents the form to upload a new file for the design item.
    Stores the uploaded file in the correct location upon POST submit
    """
    # the part number must be valid
    try:
        pn = PartNumber(partno)
    except ValueError:
        abort(404)

    # the revision must be specified
    if pn.revision is None:
        abort(404)

    # check the data
    obj = _load_if_unreleased(pn.base_number)

    # ensure the desired revision exists
    num_revisions = len(obj.get('revisions', list()))
    if pn.revision_number >= num_revisions:
        abort(404)
    pn.set_num_revisions(num_revisions)

    if pn.is_outdated():
        flash('cannot upload files to outdated revisions', 'error')
        return redirect(url_for('components.details', partno=partno))

    form = UploadForm(request.form)
    # WTF is NOT used for the file handling, since the file upload handling seems broken.
    file = request.files.get('file')
    if request.method == 'POST' and form.validate_on_submit() and file:
        try:
            filename = secure_filename(file.filename)
            dir = os.path.join(current_app.config['LPM_COMPONENT_FILES_DIR'], partno)
            if not os.path.exists(dir):
                os.makedirs(dir)
            path = os.path.join(dir, filename)
            file.save(path)
            flash('file successfully uploaded', 'success')
            return redirect(url_for('components.details', partno=partno))
        except Exception as e:
            flash(e, 'error')
    extract_errors(form)
    return render_template('components/upload_form.html', form=form, partno=partno)


@bp.route('/<partno>/new-revision', methods=['GET', 'POST'])
@role_required('component_edit')
def new_revision(partno):
    """
    Presents the form to add a new revision, and creates it upon POST submit
    """
    _load_if_released(partno)  # ensures the component exists and is released
    form = RevisionForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        now = datetime.now()
        result = current_app.mongo.db.components.update_one(
                filter={'_id': partno},
                update={
                    '$set': {
                        'released': False  # a new revision is not already released
                    },
                    '$push': {
                        'revisions': {
                            'date': now,
                            'comment': form.comment.data
                        },
                        'history': {
                            'date': now,
                            'user': current_user.id,
                            'message': 'new revision created'
                        }
                    }
                }
        )
        if result.modified_count == 1:
            flash('new revision created', 'success')
        else:
            # should not happen.
            flash('no data modified, please contact the administrator', 'error')
        return redirect(url_for('components.details', partno=partno))

    extract_errors(form)
    return render_template('components/revision_form.html', form=form, partno=partno)


@bp.route('/<partno>/release', methods=['GET', 'POST'])
@role_required('component_admin')
def release(partno):
    """
    Releases the component when a POST form is submitted
    """
    obj = _load_if_unreleased(partno)
    form = ReleaseForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        result = current_app.mongo.db.components.update_one(
                filter={'_id': partno},
                update={
                    '$set': {
                        'released': True
                    },
                    '$push': {
                        'history': {
                            'date': datetime.now(),
                            'user': current_user.id,
                            'message': 'released'
                        }
                    }
                }
        )
        if result.modified_count == 1:
            flash('component released', 'success')
        else:
            # should not happen.
            flash('no data modified, please contact the administrator', 'error')
        return redirect(url_for('components.details', partno=partno))
    extract_errors(form)
    return render_template('components/release_form.html', data=obj, form=form)


@bp.route('/<partno>/unrelease', methods=['GET', 'POST'])
@role_required('component_admin')
def unrelease(partno):
    """
    Un-releases the component when a POST form is submitted
    """
    obj = _load_if_released(partno)
    form = UnReleaseForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        result = current_app.mongo.db.components.update_one(
                filter={'_id': partno},
                update={
                    '$set': {
                        'released': False
                    },
                    '$push': {
                        'history': {
                            'date': datetime.now(),
                            'user': current_user.id,
                            'message': 'un-released'
                        }
                    }
                }
        )
        if result.modified_count == 1:
            flash('component un-released', 'success')
        else:
            # should not happen.
            flash('no data modified, please contact the administrator', 'error')
        return redirect(url_for('components.details', partno=partno))
    extract_errors(form)
    return render_template('components/unrelease_form.html', data=obj, form=form)


@bp.route('/<partno>/make-obsolete', methods=['GET', 'POST'])
@role_required('component_admin')
def make_obsolete(partno):
    """
    Marks the given component as obsolete.
    Precondition: The user must have the admin role and the item must not already be obsolete
    """
    obj = _load_if_active(partno)
    form = ObsoleteForm(request.form)
    if request.method == 'POST' and form.validate_on_submit():
        result = current_app.mongo.db.components.update_one(
                filter={'_id': partno},
                update={
                    '$set': {
                        'obsolete': True
                    },
                    '$push': {
                        'history': {
                            'date': datetime.now(),
                            'user': current_user.id,
                            'message': 'component obsoleted'
                        }
                    }
                }
        )
        if result.modified_count == 1:
            flash('component obsoleted', 'success')
        else:
            # should not happen.
            flash('no data modified, please contact the administrator', 'error')
        return redirect(url_for('components.details', partno=partno))
    extract_errors(form)
    return render_template('components/obsolete_form.html', data=obj, form=form)


def ensure_exists(partno):
    """
    Ensures that the given part number does exist in the database and raises
    ValueError if the item does not exist.
    """
    obj = current_app.mongo.db.components.find_one(partno)
    if not obj:
        raise ValueError('unknown part number %s' % partno)


def _create_new_partno():
    """
    Creates and returns a new part number (component ID).
    The new number is retrieved from the database and prefixed with the configured prefix
    """
    data = current_app.mongo.db.unique_numbers.find_one_and_update(
            {'_id': 'partno'},
            {'$inc': {'seq': 1}},
            upsert=True,  # creates the item if needed
            return_document=ReturnDocument.AFTER
    )

    prefix = current_app.config.get('LPM_PARTNO_PREFIX', '')
    return '%s%04d' % (prefix, data['seq'])


def _get_files(partno):
    """
    Returns a list of files belonging to the given part number
    """
    try:
        dir = os.path.join(current_app.config['LPM_COMPONENT_FILES_DIR'], partno)
        return sorted(os.listdir(dir))
    except:
        return list()


def _load_if_active(partno):
    """
    Loads the component with given ID from the database and returns it.
    Aborts with 404 if the component is not found.
    Flashes an error message and redirects to the details page if the component is obsolete
    """
    obj = current_app.mongo.db.components.find_one_or_404(partno)
    if obj.get('obsolete', True):
        flash('Invalid operation for obsolete components', 'error')
        abort(redirect(url_for('components.details', partno=partno)))
    return obj


def _load_if_released(partno):
    """
    Loads the component with given ID from the database and returns it.
    Aborts with 404 if the component is not found.
    Flashes an error message and redirects to the details page if the component is not released
    """
    obj = _load_if_active(partno)
    if not obj.get('released', False):
        flash('Invalid operation for non-released components', 'error')
        abort(redirect(url_for('components.details', partno=partno)))
    return obj


def _load_if_unreleased(partno):
    """
    Loads the component with given ID from the database and returns it.
    Aborts with 404 if the component is not found.
    Flashes an error message and redirects to the details page if the component is not released
    """
    obj = _load_if_active(partno)
    if obj.get('released', True):
        flash('Invalid operation for released components', 'error')
        abort(redirect(url_for('components.details', partno=partno)))
    return obj


def _extract_suppliers(form):
    """
    Extracts the list of suppliers from the form data
    """
    suppliers = list()
    if form.supplier1.data:
        suppliers.append({'name': form.supplier1.data, 'partno': form.supplier1part.data})
    if form.supplier2.data:
        suppliers.append({'name': form.supplier2.data, 'partno': form.supplier2part.data})
    return suppliers


def _extract_manufacturers(form):
    """
    Extracts the list of manufacturers from the form data
    """
    manufacturers = list()
    if form.manufacturer1.data:
        manufacturers.append({'name': form.manufacturer1.data, 'partno': form.manufacturer1part.data})
    if form.manufacturer2.data:
        manufacturers.append({'name': form.manufacturer2.data, 'partno': form.manufacturer2part.data})
    return manufacturers


def _get_categories():
    return [(c, c) for c in current_app.config.get('LPM_COMPONENT_CATEGORIES', set())]


class PartNumber:
    """
    Class that encapsulates parsing and revision handling of part numbers
    """

    pattern = re.compile('^([A-Z]+\d{4})([a-z])?$')

    def __init__(self, partno):
        match = PartNumber.pattern.match(partno)
        if not match:
            raise ValueError("string '%s' is not a valid part number" % str)
        self._baseno = match.group(1)
        self._rev = match.group(2)
        self._num_revisions = None

    def set_num_revisions(self, num_revisions):
        """
        Sets the number of revisions and assigns the latest revision if the revision has not been already set.
        The number of revisions must be > 0
        """
        assert num_revisions > 0
        self._num_revisions = num_revisions
        if self._rev is None:
            self._rev = PartNumber.revision_repr(num_revisions-1)

    @property
    def id(self):
        v = self._baseno
        if self._rev is not None:
            v += self._rev
        return v

    @property
    def base_number(self):
        return self._baseno

    @property
    def revision(self):
        return self._rev

    @property
    def revision_number(self):
        return None if self._rev is None else ord(self._rev) - ord('a')

    def is_outdated(self):
        """
        Returns whether the given revision is outdated. The number of revisions must have been set previously
        """
        assert self._num_revisions is not None
        assert self._rev is not None
        return self._num_revisions > self.revision_number+1

    @classmethod
    def revision_repr(cls, revision):
        return chr(revision + ord('a'))

    def revision_id(self, revision):
        return self._baseno + PartNumber.revision_repr(revision)

    def __repr__(self):
        return self.id
