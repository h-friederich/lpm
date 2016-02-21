from bson.json_util import loads, dumps
from testsuite import DataBaseTestCase


class ExtApiTest(DataBaseTestCase):

    def test_item_filter(self):
        # insufficient privileges -> redirect to login
        rv = self.open_with_auth('/ext/items', username='worker', method='POST',
                                 data=dict(filter='{"partno": "TE0001a"}'))
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        rv = self.open_with_auth('/ext/items', username='viewer', method='POST',
                                 data=dict(filter='{"partno": "TE0001a"}'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        self.assertEqual(['LP0001'], data.get('serials'))
        rv = self.open_with_auth('/ext/items', username='viewer', method='POST',
                                 data=dict())
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertFalse(data.get('ok'))
        self.assertIn('missing filter', data.get('message'))
        rv = self.open_with_auth('/ext/items', username='viewer', method='POST',
                                 data=dict(filt='{"$partno": "TE0001a"}'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertFalse(data.get('ok'))
        self.assertIn('missing filter', data.get('message'))

    def test_item_info(self):
        # insufficient privileges -> redirect to login
        rv = self.open_with_auth('/ext/items/LP0001', username='worker')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        rv = self.open_with_auth('/ext/items/LP0001')
        self.assertEqual(200, rv.status_code)
        obj = loads(rv.data.decode('utf-8'))
        refobj = {
            '_id': 'LP0001',
            'partno': 'TE0001a',
            'available': True,
            'status': '',
            'comments': []
        }
        self.assertEqual(refobj, obj)

    def test_item_update(self):
        # insufficient privileges -> redirect to login
        rv = self.open_with_auth('/ext/items/update/LP0001', username='worker', method='POST',
                                 data=dict(comment='some comment'))
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        rv = self.open_with_auth('/ext/items/update/LP0002', username='viewer', method='POST',
                                 data=dict(comment='some comment'))
        self.assertEqual(404, rv.status_code)
        rv = self.open_with_auth('/ext/items/update/LP0001', username='viewer', method='POST',
                                 data=dict(comment='some comment'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            comments = obj.get('comments')
            self.assertEqual(1, len(comments))
            comment = comments[0]
            self.assertEqual('some comment', comment.get('message'))
        rv = self.open_with_auth('/ext/items/update/LP0001', username='admin', method='POST',
                                 data=dict(set='{"key1": "B", "key2": 5.4}',
                                           push='{"key3": {"$each": [5, 6]}}',
                                           status='obsolete'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            comments = obj.get('comments')
            self.assertEqual(2, len(comments))
            comment = comments[0]
            self.assertEqual('some comment', comment.get('message'))
            comment = comments[1]
            self.assertEqual("[Auto] changed status to 'obsolete'", comment.get('message'))
            self.assertEqual('B', obj.get('key1'))
            self.assertEqual(5.4, obj.get('key2'))
            self.assertEqual([5, 6], obj.get('key3'))
        rv = self.open_with_auth('/ext/items/update/LP0001', username='admin', method='POST',
                                 data=dict(set='{"key4": 2}',
                                           update='{"key1": "C", "key2": 5.5}',
                                           push='{"key3": {"$each": [5, 6]}}',
                                           comment='a new comment'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        with self.app.app_context():
            obj = self.app.mongo.db.items.find_one('LP0001')
            comments = obj.get('comments')
            self.assertEqual(3, len(comments))
            comment = comments[0]
            self.assertEqual('some comment', comment.get('message'))
            comment = comments[1]
            self.assertEqual("[Auto] changed status to 'obsolete'", comment.get('message'))
            comment = comments[2]
            self.assertEqual('a new comment', comment.get('message'))
            self.assertEqual('C', obj.get('key1'))
            self.assertEqual(5.5, obj.get('key2'))
            self.assertEqual([5, 6, 5, 6], obj.get('key3'))
            self.assertEqual(2, obj.get('key4'))
        rv = self.open_with_auth('/ext/items/update/LP0001', username='admin', method='POST',
                                 data=dict(update='{"key4": "C"}'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertFalse(data.get('ok'))
        self.assertEqual("No permission to update key 'key4'", data.get('message'))
        rv = self.open_with_auth('/ext/items/update/LP0001', username='admin', method='POST',
                                 data=dict(set='{"key4": "E"}'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertFalse(data.get('ok'))
        self.assertEqual("operation would overwrite existing entry 'key4'", data.get('message'))
        rv = self.open_with_auth('/ext/items/update/LP0001', username='admin', method='POST',
                                 data=dict(set='{"key5": "E"}', status='test'))
        self.assertEqual(200, rv.status_code)
        data = loads(rv.data.decode('utf-8'))
        self.assertFalse(data.get('ok'))
        self.assertEqual("unknown status: 'test'", data.get('message'))



