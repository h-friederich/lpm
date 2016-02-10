# -*- coding: utf-8 -*-
"""
lpm is a lightweight production management system

:copyright: (c) 2016 Hannes Friederich.
:license: BSD, see LICENSE for more details.
"""

from flask.ext.pymongo import PyMongo
from . import login, utils, items, stock, components, ext, debug


def init(app):

    app.mongo = PyMongo(app)
    app.jinja_env.add_extension('jinja2.ext.do')

    login.init(app)
    utils.init(app)

    app.register_blueprint(login.bp, url_prefix='')
    app.register_blueprint(items.bp, url_prefix='/items')
    app.register_blueprint(stock.bp, url_prefix='/stock')
    app.register_blueprint(components.bp, url_prefix='/components')
    app.register_blueprint(ext.bp, url_prefix='/ext')
    app.register_blueprint(debug.bp, url_prefix='/debug')