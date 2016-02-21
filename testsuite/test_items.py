from datetime import datetime
from flask import get_flashed_messages
from flask.ext.login import login_user, logout_user
from testsuite import DataBaseTestCase
from lpm import items, auth
from lpm.components import PartNumber


class ItemsTest(DataBaseTestCase):

    def test_create_comment(self):
        with self.app.test_request_context():
            usr = auth.auth_user('viewer', '1234')
            login_user(usr)
            c = items.create_comment('comment')
            self.assertEqual('viewer', c.get('user'))
            self.assertEqual('comment', c.get('message'))
            # don't test the date
            date = datetime.now()
            c = items.create_comment('comment', date)
            self.assertEqual({'user': 'viewer', 'date': date, 'message': 'comment'}, c)
            logout_user()

    def test_store_items(self):
        with self.app.test_request_context():
            usr = auth.auth_user('viewer', '1234')
            login_user(usr)
            importdata = [
                {
                    'serial': 'LPM0001',
                    'partno': 'TE0002a',
                    'project': 'some project',
                    'status': 'shipped',
                    'param1': 'some param',
                    'batch': 'b1'
                },
                {
                    'serial': 'LPM0002',
                    'partno': 'TE0001b',
                    'param2': 'testdata',
                    'comment': 'my comment'
                },
                {
                    'serial': 'LPM0003',
                    'partno': 'TE0002a',
                    'batch': 'b1'
                },
            ]
            items._store_items(importdata)
            obj = self.app.mongo.db.items.find_one('LPM0001')
            self.assertIsNotNone(obj)
            self.assertEqual('TE0002a', obj.get('partno'))
            self.assertEqual('some project', obj.get('project'))
            self.assertEqual('shipped', obj.get('status'))
            self.assertFalse(obj.get('available'))
            self.assertEqual('b1', obj.get('batch'))
            self.assertEqual('some param', obj.get('param1'))
            comments = obj.get('comments', list())
            self.assertEqual(1, len(comments))
            comment = comments[0]
            self.assertEqual('viewer', comment.get('user'))
            self.assertEqual('[Auto] created', comment.get('message'))
            obj = self.app.mongo.db.items.find_one('LPM0002')
            self.assertIsNotNone(obj)
            self.assertEqual('TE0001b', obj.get('partno'))
            self.assertEqual('', obj.get('project'))
            self.assertEqual('', obj.get('status'))
            self.assertTrue(obj.get('available'))
            self.assertEqual('testdata', obj.get('param2'))
            comments = obj.get('comments', list())
            self.assertEqual(2, len(comments))
            comment = comments[0]
            self.assertEqual('viewer', comment.get('user'))
            self.assertEqual('[Auto] created', comment.get('message'))
            comment = comments[1]
            self.assertEqual('viewer', comment.get('user'))
            self.assertEqual('my comment', comment.get('message'))
            obj = self.app.mongo.db.items.find_one('LPM0003')
            self.assertIsNotNone(obj)
            self.assertEqual('TE0002a', obj.get('partno'))
            self.assertEqual('b1', obj.get('batch'))
            self.assertTrue(obj.get('available'))
            comments = obj.get('comments', list())
            self.assertEqual(1, len(comments))
            comment = comments[0]
            self.assertEqual('viewer', comment.get('user'))
            self.assertEqual('[Auto] created', comment.get('message'))
            # also test that the stock is correctly updated
            obj = self.app.mongo.db.stock.find_one('TE0001')
            self.assertIsNotNone(obj)
            self.assertEqual(97, obj.get('quantity'))  # 100 - 4 + 1
            obj = self.app.mongo.db.stock.find_one('TE0002')
            self.assertIsNotNone(obj)
            self.assertEqual(37, obj.get('quantity'))
            obj = self.app.mongo.db.stock_batches.find_one({'partno': 'TE0002', 'name': 'b1'})
            self.assertIsNotNone(obj)
            self.assertEqual(2, obj.get('quantity'))
            entries = self.app.mongo.db.stock_history.find({'partno': 'TE0002'}).count()
            self.assertEqual(1, entries)  # one entry for the insertion
            entries = self.app.mongo.db.stock_history.find({'partno': 'TE0001'}).count()
            self.assertEqual(2, entries)  # one entry for the insertion, one for the stock removal
            logout_user()

    def test_get_requiremets(self):
        with self.app.app_context():
            refreqs = dict(
                    required_fields=['param5', 'param6', 'param7', 'param8'],
                    date_fields=['param5'],
                    integer_fields=['param2', 'param6'],
                    floating_point_fields=['param7'],
                    boolean_fields=['param8']
            )
            reqs = items.get_requirements(PartNumber('TE0001a'))
            self.assertEqual(refreqs, reqs)
            reqs = items.get_requirements(PartNumber('TE0001b'))
            self.assertEqual(dict(), reqs)
            refreqs = dict(
                    required_fields=['param1', 'param2', 'param3', 'param4'],
                    integer_fields=['param2']
            )
            reqs = items.get_requirements(PartNumber('TE0002a'))
            self.assertEqual(refreqs, reqs)
            reqs = items.get_requirements(PartNumber('TE0002b'))
            self.assertEqual(refreqs, reqs)
            reqs = items.get_requirements(PartNumber('TE0002'))
            self.assertEqual(refreqs, reqs)

    def test_process_requirements(self):
        items.process_requirements(dict(serial=5, b='c', d='e'), dict())
        date = datetime.now()
        data = dict(
                p1='a',
                p2=date,
                p3='4.6',
                p4='6',
                p5='NO'
        )
        reqs = dict(
                date_fields=['p2'],
                integer_fields=['p4'],
                floating_point_fields=['p3'],
                boolean_fields=['p5']
        )
        items.process_requirements(data, reqs)
        self.assertEqual('a', data.get('p1'))   # unchanged
        self.assertEqual(date, data.get('p2'))  # unchanged
        self.assertTrue(isinstance(data.get('p3'), float))  # to floating point
        self.assertEqual(4.6, data.get('p3'))
        self.assertTrue(isinstance(data.get('p4'), int))  # to integer
        self.assertEqual(6, data.get('p4'))
        self.assertTrue(isinstance(data.get('p5'), bool))  # to boolean
        self.assertFalse(data.get('p5'))
        with self.assertRaises(ValueError):
            items.process_requirements(
                    dict(serial=5),
                    dict(required_fields='param1')
            )
        with self.assertRaises(ValueError):
            items.process_requirements(
                dict(param1='1234'),
                dict(date_fields='param1')
            )
        with self.assertRaises(ValueError):
            items.process_requirements(
                dict(param1='6.1'),
                dict(integer_fields=['param1'])
            )
        with self.assertRaises(ValueError):
            items.process_requirements(
                dict(param1='6.1f'),
                dict(floating_point_fields=['param1'])
            )
        with self.assertRaises(ValueError):
            items.process_requirements(
                dict(param1='6.1f'),
                dict(boolean_fields=['param1'])
            )
        with self.app.app_context():
            with self.assertRaises(ValueError):  # invalid initial status
                items.process_requirements(
                    dict(partno='TE0002a', status='somestatus'),
                    dict()
                )

    def test_do_import_file(self):
        with self.app.test_request_context():
            success, headers, data = items._import_file('testsuite/files/items_add.xlsx')
            self.assertTrue(success)
            refhdr = ['serial', 'partno', 'batch', 'param1', 'param2', 'param3', 'param5',
                      'param4', 'param6', 'param7', 'param8', 'comment']
            self.assertEqual(refhdr, headers)
            self.assertEqual(4, len(data))
            d = data[0]
            refd = dict(
                    serial='LPM0001',
                    partno='TE0001a',
                    batch='b1',
                    param5=datetime(2016, 1, 31, 15, 38, 4),
                    param6=3,
                    param7=4.6,
                    param8=True,
            )
            self.assertEqual(refd, d)
            d = data[1]
            refd = dict(
                    serial='LPM0002',
                    partno='TE0001b',
                    batch='b1',
                    param2='7',
                    param5='2016-02-01 15:38:50',  # not defined as a date field
                    param6='4',
                    param7='4.3',
                    param8='False',
            )
            self.assertEqual(refd, d)
            d = data[2]
            refd = dict(
                    serial='LPM0003',
                    partno='TE0001a',
                    batch='b1',
                    param5=datetime(2016, 2, 2, 15, 38, 9),
                    param6=5,
                    param7=2.0,
                    param8=False,
                    comment='some comment here',
            )
            self.assertEqual(refd, d)
            d = data[3]
            refd = dict(
                    serial='LPM0004',
                    partno='TE0002a',
                    batch='b2',
                    param1='a',
                    param2=5,
                    param3='7',
                    param5='n',
                    param4='d',
                    param8='text',
            )
            self.assertEqual(refd, d)

    def test_bad_import(self):
        with self.app.test_request_context():
            usr = auth.auth_user('viewer', '1234')
            login_user(usr)
            success, headers, data = items._import_file('testsuite/files/badimport.xlsx')
            self.assertFalse(success)
            msg = get_flashed_messages()
            refmsg=[
                "field 'param5' must be a datetime object (row 2)",
                "serial number 'LP0001' exists already (row 3)",
                "required field 'param5' is missing (row 4)",
                'unknown part number TE0012 (row 5)',
                'part number requires a revision (row 6)'
            ]
            self.assertEqual(refmsg, msg)

    def test_import_file(self):
        self.login('viewer')
        rv = self.client.get('/items/import')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/items/import')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/items/import', data=dict(
            file=open('testsuite/files/items_add.xlsx', 'rb')
        ))
        self.assertEqual(200, rv.status_code)
        start = rv.data.find(b'lpm_tmp_')
        end = rv.data.find(b'"', start)
        filename = rv.data[start:end]
        rv = self.client.post('/items/import', data=dict(
            tmpname=filename.decode('utf-8')
        ))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            # Only test that the objects are created.
            # The actual import logic is tested in the other test functions
            obj = self.app.mongo.db.items.find_one('LPM0001')
            self.assertIsNotNone(obj)
            obj = self.app.mongo.db.items.find_one('LPM0002')
            self.assertIsNotNone(obj)
            obj = self.app.mongo.db.items.find_one('LPM0003')
            self.assertIsNotNone(obj)
            obj = self.app.mongo.db.items.find_one('LPM0004')
            self.assertIsNotNone(obj)

    def test_check_status(self):
        with self.app.test_request_context():
            usr = auth.auth_user('admin', '1234')
            login_user(usr)
            items._check_status('TE0002a', '', 'tested')
            items._check_status('TE0002a', '', 'reserved')
            with self.assertRaises(ValueError):
                items._check_status('TE0002a', '', 'shipped')  # invalid transition
            with self.assertRaises(ValueError):
                items._check_status('TE0002a', '', 'somestatus')  # unknown status
            items._check_status('TE0002a', 'reserved', 'shipped')  # now a valid transition
            logout_user()
            usr = auth.auth_user('viewer', '1234')
            login_user(usr)
            with self.assertRaises(ValueError):
                items._check_status('TE0002a', '', 'tested')  # requires item_admin
            logout_user()
            usr = auth.auth_user('admin', '1234')
            login_user(usr)
            with self.assertRaises(ValueError):
                items._check_status('TE0001a', '', 'tested')  # unknown status for this part number
            items._check_status('TE0001a', '', 'obsolete')
            logout_user()

    def test_is_unavailable(self):
        with self.app.app_context():
            self.assertFalse(items._is_unavailable('TE0002a', 'tested'))
            self.assertFalse(items._is_unavailable('TE0002a', 'reserved'))
            self.assertTrue(items._is_unavailable('TE0002a', 'shipped'))
            self.assertTrue(items._is_unavailable('TE0002a', 'obsolete'))
            self.assertTrue(items._is_unavailable('TE0001a', 'obsolete'))

    def test_add_comment(self):
        self.login('viewer')
        rv = self.client.get('/items/LP0001/add-comment')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/items/LP0001/add-comment', data=dict(
            message='testcomment'
        ))
        self.assertEqual(302, rv.status_code)
        self.logout()
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            comments = obj.get('comments')
            self.assertEqual(1, len(comments))
            comment = comments[0]
            self.assertEqual('testcomment', comment.get('message'))
            self.assertEqual('viewer', comment.get('user'))
            self.assertTrue(obj.get('available'))
            self.assertEqual('', obj.get('status'))

    def test_change_status(self):
        self.login('viewer')
        rv = self.client.get('/items/LP0001/change-status/teststatus')
        self.assertEqual(200, rv.status_code)
        self.assertTrue(
                b'<input class="form-control" id="status" name="status" '
                b'placeholder="Required" type="text" value="teststatus">'
                in rv.data
        )
        rv = self.client.post('/items/LP0001/change-status', data=dict(
            status='teststatus',
            project='someproject',
            comment='should not work'
        ))
        self.assertEqual(200, rv.status_code)  # invalid state transition
        self.assertTrue(b'unknown status: &#39;teststatus&#39;' in rv.data)
        rv = self.client.post('/items/LP0001/change-status', data=dict(
            status='obsolete',
            project='someproject',
            comment='should not work'
        ))
        self.assertEqual(200, rv.status_code)  # insufficient permissions
        self.assertTrue(
                b"insufficient permissions to do the status transition from &#39;&#39; to &#39;obsolete&#39;"
                in rv.data
        )
        self.logout()
        self.login('admin')
        rv = self.client.post('/items/LP0001/change-status', data=dict(
            status='obsolete',
            project='someproject',
            comment='should now work'
        ))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            self.assertEqual('obsolete', obj.get('status'))
            self.assertFalse(obj.get('available'))
            self.assertEqual('someproject', obj.get('project'))
            comments = obj.get('comments')
            self.assertEqual(2, len(comments))
            comment = comments[0]
            self.assertEqual("[Auto] changed status to 'obsolete'", comment.get('message'))
            self.assertEqual('admin', comment.get('user'))
            comment = comments[1]
            self.assertEqual('should now work', comment.get('message'))
            self.assertEqual('admin', comment.get('user'))

    def test_set_project(self):
        self.login('viewer')
        rv = self.client.get('/items/LP0001/set-project')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/items/LP0001/set-project', data=dict(
            project='myproject'
        ))
        self.assertEqual(302, rv.status_code)
        self.logout()
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            self.assertEqual('myproject', obj.get('project'))
            comments = obj.get('comments')
            self.assertEqual(1, len(comments))
            comment = comments[0]
            self.assertEqual("[Auto] changed project association to 'myproject'", comment.get('message'))
            self.assertEqual('viewer', comment.get('user'))
            self.assertTrue(obj.get('available'))
            self.assertEqual('', obj.get('status'))
