# -*- coding: utf-8 -*-
import unittest
import base64
import dateutil.parser
from flask import Flask
import lpm


class TestCase(unittest.TestCase):
    """
    Base test case that configures the Flask app for testing
    """

    def setUp(self):
        self.app = Flask('lpm_test')
        self.app.config.update(
                DEBUG=True,
                SECRET_KEY=b'\xfeb\xba\x0eU\xb7\xd1\xdd\xe05k\x9eF%\xf93&r\xe3y\xe7\x9c\xac\x9a',
                MONGO_DBNAME='lpm_test',
                WTF_CSRF_ENABLED=False,
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
                            roles={'login', 'request_login'},
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
                LPM_COMPONENT_CATEGORIES={'category1', 'category2'},
                LPM_COMPONENT_FILES_DIR='/tmp',
                LPM_ITEM_VIEW_MAP={
                    'TE0002': 'TE0002.html',
                    'TE0001a': 'TE0001a.html',
                    'TE0001b': 'TE0001b.html',
                },
                LPM_ITEM_IMPORT_MAP={
                    'TE0002': dict(
                        required_fields=['param1', 'param2', 'param3', 'param4'],
                        integer_fields=['param2'],
                    ),
                    'TE0001a': dict(
                        required_fields=['param5', 'param6', 'param7', 'param8'],
                        date_fields=['param5'],
                        integer_fields=['param2', 'param6'],
                        floating_point_fields=['param7'],
                        boolean_fields=['param8']
                    )
                },
                LPM_ITEM_STATUS_MAP={
                    'TE0002': {
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
                    'TE0001a': {'key1', 'key2'},
                    'default': set(),
                },
        )
        lpm.init(self.app)
        self.client = self.app.test_client()

    def login(self, username='admin', password='1234'):
        return self.client.post('/login',
                                data=dict(username=username,
                                          password=password),
                                follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def open_with_auth(self, url, method='GET', data=None, username='admin', **kwargs):
        """
        Helper function that requests a page with basic authorization header
        """
        value = (username + ':1234').encode('utf-8')
        headers = {
            'Authorization': b'Basic ' + base64.b64encode(value)
        }
        return self.client.open(url, method=method, headers=headers, data=data, **kwargs)


class DataBaseTestCase(TestCase):
    """
    Ensures that the test database is in a known 'clean' state
    """

    def setUp(self):
        TestCase.setUp(self)

        # ensure the database is in a known state
        with self.app.app_context():
            db = self.app.mongo.db
            if db.name != 'lpm_test':
                raise EnvironmentError('Cannot run data-base related unit tests when a non-test database is chosen.')

            # setup fixed, known data in the database for the tests
            db.components.drop()
            db.stock.drop()
            db.stock_batches.drop()
            db.stock_history.drop()
            db.items.drop()
            db.unique_numbers.drop()

            db.components.insert([
                {
                    '_id': 'TE0001',
                    'name': 'Test Item 1',
                    'decscription': 'Some description here',
                    'suppliers': [
                        {'name': 'Digi Key', 'partno': '1234-1-ND'},
                        {'name': 'Mouser', 'partno': '2345'},
                    ],
                    'manufacturers': [
                        {'name': 'Panasonic', 'partno': 'P100ERJX' }
                    ],
                    'revisions': [
                        {
                            'date': dateutil.parser.parse('2016-01-12T07:28:00Z'),
                            'comment': 'comment 1'
                        },
                        {
                            'date': dateutil.parser.parse('2016-01-14T08:28:00.200Z'),
                            'comment': 'comment 2'
                        }
                    ],
                    'released': False,
                    'obsolete': False,
                    'history': [
                        {
                            'date': dateutil.parser.parse('2016-01-12T07:28:00Z'),
                            'user': "worker",
                            'message': "added info"
                        },
                        {
                            'date': dateutil.parser.parse("2016-01-14T08:28:00Z"),
                            'user': 'admin',
                            'message': 'more info'
                        },
                    ]
                },
                {
                    '_id': 'TE0002',
                    'name': 'Test Item 2',
                    'decscription': 'Some description here',
                    'suppliers': [
                        {'name': 'Digi Key', 'partno': '2345-1-ND'},
                    ],
                    'manufacturers': [
                        {'name': 'Panasonic', 'partno': 'P110ERJX' }
                    ],
                    'revisions': [
                        {
                            'date': dateutil.parser.parse('2016-01-21T18:02:35Z'),
                            'comment': 'comment 1'
                        },
                    ],
                    'released': True,
                    'obsolete': False,
                    'history': [
                        {
                            'date': dateutil.parser.parse('2016-01-21T19:03:36Z'),
                            'user': "worker",
                            'message': "created"
                        },
                    ]
                },
                {
                    '_id': 'TE0003',
                    'name': 'Test Item 3',
                    'decscription': 'Some description here',
                    'suppliers': [
                        {'name': 'Digi Key', 'partno': '2345-1-ND'},
                    ],
                    'manufacturers': [
                        {'name': 'Panasonic', 'partno': 'P110ERJX' }
                    ],
                    'revisions': [
                        {
                            'date': dateutil.parser.parse('2016-01-21T18:02:35Z'),
                            'comment': 'comment 1'
                        },
                    ],
                    'released': True,
                    'obsolete': True,
                    'history': [
                        {
                            'date': dateutil.parser.parse('2016-01-21T19:03:36Z'),
                            'user': "worker",
                            'message': "created"
                        },
                    ]
                },
                {
                    '_id': 'TE0004',
                    'name': 'Test Item 4',
                    'decscription': 'Some description here',
                    'suppliers': [ ],
                    'manufacturers': [ ],
                    'revisions': [
                        {
                            'date': dateutil.parser.parse('2016-01-26T17:50:24Z'),
                            'comment': 'comment 1'
                        },
                    ],
                    'released': True,
                    'obsolete': False,
                    'history': [ ]
                },
            ])
            db.stock.insert([
                {
                    '_id': 'TE0001',
                    'quantity': 100,
                },
                {
                    '_id': 'TE0002',
                    'quantity': 35,
                    'bom': [
                        {
                            'partno': 'TE0001',
                            'quantity': 2
                        },
                        {
                            'partno': 'TE0003',
                            'quantity': 1
                        },
                    ]
                },
                {
                    '_id': 'TE0003',
                    'quantity': 20,
                    'bom': [
                        {
                            'partno': 'TE0001',
                            'quantity': 1
                        },
                    ]
                },
            ])
            db.stock_batches.insert([
                {
                    'partno': 'TE0001',
                    'name': 'batch1',
                    'quantity': 10,
                }
            ])
            db.items.insert({
                '_id': 'LP0001',
                'partno': 'TE0001a',
                'available': True,
                'status': '',
                'comments': []
            })

