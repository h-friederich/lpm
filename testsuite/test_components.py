import os
import shutil
from io import BytesIO
from werkzeug.exceptions import NotFound, HTTPException
from testsuite import DataBaseTestCase
from lpm import components


class ComponentTest(DataBaseTestCase):

    def test_parse_partno(self):
        pn = components.PartNumber('AB0032')
        self.assertEqual('AB0032', pn.id)
        self.assertEqual('AB0032', pn.base_number)
        self.assertIsNone(pn.revision)
        self.assertIsNone(pn.revision_number)
        self.assertEqual('AB0032', str(pn))
        pn.set_num_revisions(5)
        self.assertEqual('AB0032e', pn.id)
        self.assertEqual('AB0032', pn.base_number)
        self.assertEqual('e', pn.revision)
        self.assertEqual(4, pn.revision_number)
        self.assertEqual('AB0032e', str(pn))
        self.assertFalse(pn.is_outdated())
        pn = components.PartNumber('AB0032c')
        self.assertEqual('AB0032c', pn.id)
        self.assertEqual('AB0032', pn.base_number)
        self.assertEqual('c', pn.revision)
        self.assertEqual(2, pn.revision_number)  # revision is zero-based
        self.assertEqual('AB0032c', str(pn))
        pn.set_num_revisions(6)
        self.assertEqual('AB0032c', pn.id)
        self.assertEqual('AB0032', pn.base_number)
        self.assertEqual('c', pn.revision)
        self.assertEqual(2, pn.revision_number)  # revision is zero-based
        self.assertEqual('AB0032c', str(pn))
        self.assertEqual('AB0032a', pn.revision_id(0))
        self.assertEqual('AB0032d', pn.revision_id(3))
        self.assertTrue(pn.is_outdated())

        with self.assertRaises(ValueError):
            components.PartNumber('AB032a')  # number too short
        with self.assertRaises(ValueError):
            components.PartNumber('AB00120')  # number too long
        with self.assertRaises(ValueError):
            components.PartNumber('AB0012aa')  # invalid revision
        with self.assertRaises(ValueError):
            components.PartNumber('AB0012_')  # invalid revision
        self.assertEqual('a', components.PartNumber.revision_repr(0))
        self.assertEqual('c', components.PartNumber.revision_repr(2))

    def test_create_partno(self):
        with self.app.app_context():
            self.assertEqual('LP0001', components._create_new_partno())
            self.assertEqual('LP0002', components._create_new_partno())

    def test_load_active(self):
        with self.app.test_request_context():
            with self.assertRaises(NotFound):
                components._load_if_active('LP0001')
            obj = components._load_if_active('TE0001')
            self.assertIsNotNone(obj)
            with self.assertRaises(HTTPException):  # obsolete
                components._load_if_active('TE0003')

    def test_load_released(self):
        with self.app.test_request_context():
            obj = components._load_if_released('TE0002')
            self.assertIsNotNone(obj)
            with self.assertRaises(HTTPException):  # not released
                components._load_if_released('TE0001')

    def test_load_unreleased(self):
        with self.app.test_request_context():
            obj = components._load_if_unreleased('TE0001')
            self.assertIsNotNone(obj)
            with self.assertRaises(HTTPException):  # already released
                components._load_if_unreleased('TE0002')

    def test_details(self):
        # redirect to the revisionless URL if the user doesn't have the component_edit role
        self.login('viewer')
        rv = self.client.get('/components/TE0001a')
        self.assertEqual(302, rv.status_code)
        self.assertTrue(rv.location.endswith('TE0001'))
        self.logout()
        # component_edit users may look at outdated components
        self.login('worker')
        rv = self.client.get('/components/TE0001a')
        self.assertEqual(200, rv.status_code)
        self.assertIn(b'outdated revision', rv.data)
        self.assertIn(b'not yet been released', rv.data)
        self.assertIn(b'(TE0001a)', rv.data)
        self.assertNotIn(b'(TE0001b)', rv.data)
        rv = self.client.get('/components/TE0001b')
        self.assertEqual(200, rv.status_code)
        self.assertNotIn(b'outdated revision', rv.data)
        self.assertIn(b'not yet been released', rv.data)
        self.assertIn(b'(TE0001b)', rv.data)
        self.assertNotIn(b'(TE0001a)', rv.data)
        rv = self.client.get('/components/TE0001')
        self.assertEqual(200, rv.status_code)
        self.assertNotIn(b'outdated revision', rv.data)
        self.assertIn(b'not yet been released', rv.data)
        self.assertIn(b'(TE0001b)', rv.data)
        self.assertNotIn(b'(TE0001a)', rv.data)
        # released component
        rv = self.client.get('/components/TE0002')
        self.assertNotIn(b'not yet been released', rv.data)
        self.assertNotIn(b'obsolete', rv.data)
        # obsolete component
        rv = self.client.get('/components/TE0003')
        self.assertNotIn(b'not yet been released', rv.data)
        self.assertIn(b'obsolete', rv.data)

    def test_details_files(self):
        if not os.path.exists('/tmp/TE0001a'):
            os.makedirs('/tmp/TE0001a')
        with open('/tmp/TE0001a/a.txt', 'w') as f:
            f.write('ad')
        with open('/tmp/TE0001a/b.txt', 'w') as f:
            f.write('b')
        self.login('worker')
        rv = self.client.get('/components/TE0001a')
        self.assertIn(b'/TE0001a/a.txt', rv.data)
        self.assertIn(b'/TE0001a/b.txt', rv.data)
        rv = self.client.get('/components/TE0001b')
        self.assertNotIn(b'a.txt', rv.data)
        self.assertNotIn(b'b.txt', rv.data)
        self.login('worker')
        rv = self.client.get('/components/TE0001a/a.txt')
        self.assertEqual(b'ad', rv.data)
        self.logout()
        self.login('viewer')
        rv = self.client.get('/components/TE0001a/a.txt')
        self.assertEqual(403, rv.status_code)  # no permission
        shutil.rmtree('/tmp/TE0001a', ignore_errors=True)

    def test_create_new(self):
        self.login()
        rv = self.client.get('/components/add')
        self.assertIn(b'<h3>New Component</h3>', rv.data)
        rv = self.client.post('/components/add')
        self.assertIn(b'<h3>New Component</h3>', rv.data)
        self.assertIn(b'name: This field is required', rv.data)
        rv = self.client.post('/components/add', data=dict(
            name='The name',
            description='Some description',
            category='category1',
            comment='really?',
            supplier1='Supplier 1',
            supplier1part='part1',
            supplier2='Supplier 2',
            supplier2part='part2',
            manufacturer1='Manufacturer 1',
            manufacturer1part='part3',
            manufacturer2='Manufacturer 2',
            manufacturer2part='part4'
        ))
        self.assertEqual(302, rv.status_code)
        self.assertIn(b'/components/LP0001', rv.data)  # redirect
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'LP0001'})
        self.assertIsNotNone(obj)
        # we don't know the date thus do not compare the entire entry
        self.assertEqual('The name', obj.get('name'))
        self.assertEqual('Some description', obj.get('description'))
        self.assertEqual('category1', obj.get('category'))
        self.assertEqual([{'name': 'Supplier 1', 'partno': 'part1'},
                          {'name': 'Supplier 2', 'partno': 'part2'}],
                         obj.get('suppliers'))
        self.assertEqual([{'name': 'Manufacturer 1', 'partno': 'part3'},
                          {'name': 'Manufacturer 2', 'partno': 'part4'}],
                         obj.get('manufacturers'))
        self.assertEqual('really?', obj.get('revisions')[0].get('comment'))
        self.assertFalse(obj.get('released'))
        self.assertFalse(obj.get('obsolete'))
        self.logout()

        # not logged in
        rv = self.client.get('/components/add', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)

        # insufficient privileges
        self.login('viewer')
        rv = self.client.get('/components/add', follow_redirects=True)
        self.assertIn(b'Please log in', rv.data)
        self.assertIn(b'insufficient privileges', rv.data)

    def test_edit(self):
        self.login('viewer')
        rv = self.client.get('/components/TE0001/edit')
        self.assertEqual(302, rv.status_code)  # component_edit role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0001/edit')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0002/edit')  # released
        self.assertEqual(302, rv.status_code)
        rv = self.client.get('/components/TE0003/edit')  # obsolete
        self.assertEqual(302, rv.status_code)
        rv = self.client.get('/components/TE0001a/edit')  # not a base number
        self.assertEqual(404, rv.status_code)
        rv = self.client.post('/components/TE0001/edit', data=dict(
            name='The name',
            description='Some description',
            comment='really?',
            category='category2',
            supplier1='Supplier 1',
            supplier1part='part1',
            supplier2='Supplier 2',
            supplier2part='part2',
            manufacturer1='Manufacturer 1',
            manufacturer1part='part3',
            manufacturer2='Manufacturer 2',
            manufacturer2part='part4'
        ))
        self.assertEqual(302, rv.status_code)
        self.assertTrue(rv.location.endswith('/components/TE0001'))
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0001'})
        self.assertIsNotNone(obj)
        # we don't know the date thus do not compare the entire entry
        self.assertEqual('The name', obj.get('name'))
        self.assertEqual('Some description', obj.get('description'))
        self.assertEqual('category2', obj.get('category'))
        self.assertEqual([{'name': 'Supplier 1', 'partno': 'part1'},
                          {'name': 'Supplier 2', 'partno': 'part2'}],
                         obj.get('suppliers'))
        self.assertEqual([{'name': 'Manufacturer 1', 'partno': 'part3'},
                          {'name': 'Manufacturer 2', 'partno': 'part4'}],
                         obj.get('manufacturers'))
        self.assertEqual('really?', obj.get('revisions')[1].get('comment'))
        self.assertFalse(obj.get('released'))
        self.assertFalse(obj.get('obsolete'))

    def test_fileupload(self):
        if not os.path.exists('/tmp/TE0001b'):
            os.makedirs('/tmp/TE0001b')
        self.login('viewer')
        rv = self.client.get('/components/TE0001b/fileupload')
        self.assertEqual(302, rv.status_code)  # component_edit role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0001b/fileupload')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0001a/fileupload')
        self.assertEqual(302, rv.status_code)  # outdated revision
        rv = self.client.get('/components/TE0002a/fileupload')
        self.assertEqual(302, rv.status_code)  # already released
        rv = self.client.get('/components/TE0003a/fileupload')
        self.assertEqual(302, rv.status_code)  # obsolete
        rv = self.client.post('/components/TE0001b/fileupload', data=dict(
            file=(BytesIO(b'123456\n789'), 'upload.txt')
        ))
        self.assertEqual(302, rv.status_code)  # uploaded
        self.assertTrue(rv.location.endswith('/components/TE0001b'))
        with open('/tmp/TE0001b/upload.txt', 'rb') as f:
            self.assertEqual(b'123456\n789', f.read())
        shutil.rmtree('/tmp/TE0001b', ignore_errors=True)

    def test_new_revision(self):
        self.login('viewer')
        rv = self.client.get('/components/TE0002/new-revision')
        self.assertEqual(302, rv.status_code)  # component_edit role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0002/new-revision')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0001/new-revision')
        self.assertEqual(302, rv.status_code)  # not released
        rv = self.client.get('/components/TE0003/new-revision')
        self.assertEqual(302, rv.status_code)  # obsolete
        rv = self.client.post('/components/TE0002/new-revision',
                              data=dict(comment='testing a new feature'))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0002'})
        self.assertIsNotNone(obj)
        revisions = obj.get('revisions')
        self.assertEqual(2, len(revisions))
        self.assertFalse(obj.get('released'))
        self.assertEqual('testing a new feature', revisions[1].get('comment'))

    def test_release(self):
        self.login('viewer')
        rv = self.client.get('/components/TE0001/release')
        self.assertEqual(302, rv.status_code)  # component_admin role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0001/release')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0002/release')
        self.assertEqual(302, rv.status_code)  # already released
        rv = self.client.get('/components/TE0003/release')
        self.assertEqual(302, rv.status_code)  # obsolete
        rv = self.client.post('/components/TE0001/release')
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0001'})
        self.assertIsNotNone(obj)
        self.assertTrue(obj.get('released'))

    def test_unrelease(self):
        self.login('viewer')
        rv = self.client.get('/components/TE0002/unrelease')
        self.assertEqual(302, rv.status_code)  # component_admin role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0002/unrelease')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0001/unrelease')
        self.assertEqual(302, rv.status_code)  # not released
        rv = self.client.get('/components/TE0003/unrelease')
        self.assertEqual(302, rv.status_code)  # obsolete
        rv = self.client.post('/components/TE0002/unrelease')
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0002'})
        self.assertIsNotNone(obj)
        self.assertFalse(obj.get('released'))

    def test_make_obsolete(self):
        self.login('viewer')
        rv = self.client.get('/components/TE0001/make-obsolete')
        self.assertEqual(302, rv.status_code)  # component_admin role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/components/TE0001/make-obsolete')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0002/make-obsolete')
        self.assertEqual(200, rv.status_code)
        rv = self.client.get('/components/TE0003/make-obsolete')
        self.assertEqual(302, rv.status_code)  # already obsolete
        rv = self.client.post('/components/TE0001/make-obsolete')
        self.assertEqual(302, rv.status_code)
        rv = self.client.post('/components/TE0002/make-obsolete')
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0001'})
        self.assertIsNotNone(obj)
        self.assertTrue(obj.get('obsolete'))
        with self.app.app_context():
            obj = self.app.mongo.db.components.find_one({'_id': 'TE0002'})
        self.assertIsNotNone(obj)
        self.assertTrue(obj.get('obsolete'))