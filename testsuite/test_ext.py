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



