#!/usr/bin/env python
import sys
import os
from flask import Flask, redirect, url_for

# ensure lpm is found and can be directly imported from this file
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lpm

app = Flask(__name__)

app.config.update(
        DEBUG=True,
        SECRET_KEY=b'2E\x9d\xe8"\xb5\xa3\x1b\xc5a6\xd8\x12:\x1ea\xf6\x91N[\xe4X\x8e\x8a',
        MONGO_DBNAME='lpm',
        LPM_AUTH_SRC='simple',
        LPM_AUTH_USERS={
            'worker': dict(
                    name='Worker',
                    password='1234',
                    roles={'login', 'component_edit'},
                    active=True,
            ),
            'admin': dict(
                    name='Admin',
                    password='1234',
                    roles={
                        'login', 'request_login',
                        'component_edit', 'component_admin',
                        'stock_admin', 'item_admin', 'db_debug',
                    },
                    active=True,
            ),
            'viewer': dict(
                    name='Viewer',
                    password='1234',
                    roles={'login'},
                    active=True,
            ),
            'disabled': dict(
                    name='Disabled User',
                    password='1234',
                    roles={'login', 'component_admin'},
                    active=False,
            ),
            'ext': dict(
                    name='External Scripts',
                    password='1234',
                    roles={'request_login', 'component_admin'},
                    active=True,
            )
        },
        LPM_PARTNO_PREFIX='LP',
        LPM_COMPONENT_FILES_DIR='/tmp',
        LPM_ITEM_VIEW_MAP={
            'LP0002': 'LP0002.html',
        },
        LPM_ITEM_IMPORT_MAP={
            'LP0002': dict(
                    required_fields=['param1'],
                    integer_fields=['param2'],
            ),
            'LP0001a': dict(
                    required_fields=['param5'],
                    date_fields=['param5'],
                    integer_fields=['param2', 'param6'],
                    floating_point_fields=['param7'],
                    boolean_fields=['param8']
            )
        },
        LPM_ITEM_STATUS_MAP={
            'LP0002': {
                'tested': dict(origins=[''], unavailable=False, role='item_admin'),
                'reserved': dict(origins=['', 'tested'], unavailable=False),
                'shipped': dict(origins=['reserved'], unavailable=True, require_admin=False),
                'obsolete': dict(origins=['', 'tested', 'reserved', 'shipped'],
                                 unavailable=True, role='item_admin')
            },
            'default': {
                'obsolete': dict(origins=[''], unavailable=True, role='item_admin')
            },
        },
        LPM_EXT_UPDATE_FIELDS={
            'default': set(),
        },
)

lpm.init(app)


@app.route('/')
def main():
    """
    main entry point, redirect to the items overview
    """
    return redirect(url_for('items.overview'))

app.run()
