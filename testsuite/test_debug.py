from bson.json_util import dumps
from testsuite import DataBaseTestCase


class DebugTest(DataBaseTestCase):

    def test_debug(self):
        self.login('viewer')
        rv = self.client.get('/debug/items/LP0001')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/debug/items/LP0001')
        self.assertEqual(200, rv.status_code)

        obj = {
            '_id': 'LP0001',
            'partno': 'TE0001b',
            'available': False,
            'status': 'test',
            'comments': []
        }
        objstr = dumps(obj)

        rv = self.client.post('/debug/items/LP0001', data=dict(document=objstr))
        self.assertEqual(200, rv.status_code)
        self.assertTrue(b'data successfully updated' in rv.data)

        with self.app.app_context():
            dbobj = self.app.mongo.db.items.find_one('LP0001')
            self.assertEqual(obj, dbobj)


