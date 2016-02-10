from testsuite import DataBaseTestCase
from lpm import stock


class StockTest(DataBaseTestCase):

    def test_update_counts(self):
        with self.app.app_context():
            stock.update_counts('TE0002', 5, 'mybatch', 'this works')
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0001'})
            self.assertIsNotNone(obj)
            self.assertEqual(90, obj.get('quantity'))  # only the direct BOM children are considered
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0002'})
            self.assertIsNotNone(obj)
            self.assertEqual(40, obj.get('quantity'))
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0003'})
            self.assertIsNotNone(obj)
            self.assertEqual(15, obj.get('quantity'))
            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0002',
                'name': 'mybatch'
            })
            self.assertIsNotNone(obj)
            self.assertEqual(5, obj.get('quantity'))
            obj = self.app.mongo.db.stock_history.find_one({
                'partno': 'TE0002',
                'delta': 5,
                'message': 'this works'
            })
            self.assertIsNotNone(obj)

            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0004'})
            self.assertIsNone(obj)
            stock.update_counts('TE0004', 5, '', 'inserted')
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0004'})
            self.assertIsNotNone(obj)
            self.assertEqual(5, obj.get('quantity'))

            with self.assertRaises(ValueError):
                stock.update_counts('TE0005', 10, '', '')  # component does not exist

    def test_correct_counts(self):
        with self.app.app_context():
            stock.correct_counts('TE0002', 5, 'my message')
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0002'})
            self.assertIsNotNone(obj)
            self.assertEqual(5, obj.get('quantity'))
            obj = self.app.mongo.db.stock_history.find_one({
                'partno': 'TE0002',
                'quantity': 5,
                'message': 'my message'
            })
            self.assertIsNotNone(obj)

    def test_update_batch(self):
        with self.app.app_context():
            stock.update_batch('TE0001', 'batch1', 10)
            stock.update_batch('TE0001', 'newbatch', 15)
            stock.update_batch('TE0001', 'otherbatch', 0)  # should be a no-op
            stock.update_batch('TE0001', '', 20)  # should be a no-op

            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0001',
                'name': 'batch1'
            })
            self.assertIsNotNone(obj)
            self.assertEqual(20, obj.get('quantity'))
            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0001',
                'name': 'newbatch'
            })
            self.assertIsNotNone(obj)
            self.assertEqual(15, obj.get('quantity'))
            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0001',
                'name': 'otherbatch'
            })
            self.assertIsNone(obj)
            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0001',
                'name': ''
            })
            self.assertIsNone(obj)

    def test_set_bom(self):
        with self.app.app_context():
            bomlist = [
                {'partno': 'TE0003', 'quantity': 5},
                {'partno': 'TE0004', 'quantity': 2},
            ]
            stock.set_bom('TE0002', bomlist)
            obj = self.app.mongo.db.stock.find_one('TE0002')
            self.assertIsNotNone(obj)
            bom = obj.get('bom')
            self.assertIsNotNone(bom)
            self.assertEqual(bomlist, bom)
            with self.assertRaises(ValueError):
                stock.set_bom('TE0345', bomlist)  # partno does not exist
            bomlist = [
                {'partno': 'TE0003', 'quantity': 5},
                {'partno': 'TE0005', 'quantity': 2},
            ]
            with self.assertRaises(ValueError):
                stock.set_bom('TE0002', bomlist)  # child partno does not exist
            # test upsert
            bomlist = [
                {'partno': 'TE0002', 'quantity': 5},
                {'partno': 'TE0001', 'quantity': 2},
            ]
            stock.set_bom('TE0004', bomlist)
            obj = self.app.mongo.db.stock.find_one('TE0004')
            self.assertIsNotNone(obj)
            bom = obj.get('bom')
            self.assertIsNotNone(bom)
            self.assertEqual(bomlist, bom)

    def test_check_bom(self):
        with self.app.app_context():
            stock._check_bom('TE0002')  # all okay
            with self.assertRaises(RuntimeError):
                stock._check_bom('TE0002', {'TE0001'})
            with self.assertRaises(RuntimeError):
                stock._check_bom('TE0003', {'TE0001'})

    def test_add_single(self):
        self.login('viewer')
        rv = self.client.get('/stock/TE0001/add-single')
        self.assertEqual(302, rv.status_code)  # stock_admin role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/stock/TE0001/add-single')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/stock/TE0001/add-single',
                              data=dict(quantity=5,
                                        batch='testbatch'))
        self.assertEqual(302, rv.status_code)
        self.assertTrue(rv.location.endswith('/stock/TE0001'))
        with self.app.app_context():
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0001'})
            self.assertIsNotNone(obj)
            self.assertEqual(105, obj.get('quantity'))
            obj = self.app.mongo.db.stock_batches.find_one({
                'partno': 'TE0001',
                'name': 'testbatch'
            })
            self.assertIsNotNone(obj)

    def test_correct_single(self):
        self.login('viewer')
        rv = self.client.get('/stock/TE0001/correct-single')
        self.assertEqual(302, rv.status_code)  # stock_admin role required
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/stock/TE0001/correct-single')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/stock/TE0001/correct-single',
                              data={'quantity': 5})
        self.assertEqual(302, rv.status_code)
        self.assertTrue(rv.location.endswith('/stock/TE0001'))
        with self.app.app_context():
            obj = self.app.mongo.db.stock.find_one({'_id': 'TE0001'})
            self.assertIsNotNone(obj)
            self.assertEqual(5, obj.get('quantity'))

    def test_add_file(self):
        self.login('viewer')
        rv = self.client.get('/stock/add')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/stock/add')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/stock/add', data=dict(
            file=open('testsuite/files/stock_add.xlsx', 'rb')
        ))
        self.assertEqual(200, rv.status_code)
        start = rv.data.find(b'lpm_tmp_')
        end = rv.data.find(b'"', start)
        filename = rv.data[start:end]
        rv = self.client.post('/stock/add', data=dict(
            tmpname=filename.decode('utf-8')
        ))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.stock.find_one('TE0001')
            self.assertIsNotNone(obj)
            self.assertEqual(86, obj.get('quantity'))  # 100 - (5*2) - (4*1)
            obj = self.app.mongo.db.stock.find_one('TE0002')
            self.assertIsNotNone(obj)
            self.assertEqual(40, obj.get('quantity'))  # 35 + 5
            obj = self.app.mongo.db.stock.find_one('TE0003')
            self.assertIsNotNone(obj)
            self.assertEqual(19, obj.get('quantity'))  # 20 - 5 + 4
            obj = self.app.mongo.db.stock.find_one('TE0004')
            self.assertIsNotNone(obj)
            self.assertEqual(2, obj.get('quantity'))  # 0 + 2
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0001'}))
            self.assertEqual(2, len(history))
            entry = history[0]
            self.assertEqual('(BOM rule)', entry.get('message'))
            self.assertEqual(-10, entry.get('delta'))
            entry = history[1]
            self.assertEqual('(BOM rule)', entry.get('message'))
            self.assertEqual(-4, entry.get('delta'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0002'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('added to stock', entry.get('message'))
            self.assertEqual(5, entry.get('delta'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0003'}))
            self.assertEqual(2, len(history))
            entry = history[0]
            self.assertEqual('(BOM rule)', entry.get('message'))
            self.assertEqual(-5, entry.get('delta'))
            entry = history[1]
            self.assertEqual('added to stock', entry.get('message'))
            self.assertEqual(4, entry.get('delta'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0004'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('added to stock', entry.get('message'))
            self.assertEqual(2, entry.get('delta'))

    def test_correct_file(self):
        self.login('viewer')
        rv = self.client.get('/stock/correct')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/stock/correct')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/stock/correct', data=dict(
            file=open('testsuite/files/stock_correct.xlsx', 'rb')
        ))
        self.assertEqual(200, rv.status_code)
        start = rv.data.find(b'lpm_tmp_')
        end = rv.data.find(b'"', start)
        filename = rv.data[start:end]
        rv = self.client.post('/stock/correct', data=dict(
            tmpname=filename.decode('utf-8')
        ))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.stock.find_one('TE0001')
            self.assertIsNotNone(obj)
            self.assertEqual(0, obj.get('quantity'))  # implicitly set to zero
            obj = self.app.mongo.db.stock.find_one('TE0002')
            self.assertIsNotNone(obj)
            self.assertEqual(15, obj.get('quantity'))  # set to 15
            obj = self.app.mongo.db.stock.find_one('TE0003')
            self.assertIsNotNone(obj)
            self.assertEqual(10, obj.get('quantity'))  # set to 10
            obj = self.app.mongo.db.stock.find_one('TE0004')
            self.assertIsNotNone(obj)
            self.assertEqual(23, obj.get('quantity'))  # created
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0001'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('missing', entry.get('message'))
            self.assertEqual(0, entry.get('quantity'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0002'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('stolen', entry.get('message'))
            self.assertEqual(15, entry.get('quantity'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0003'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('manual correction', entry.get('message'))
            self.assertEqual(10, entry.get('quantity'))
            history = list(self.app.mongo.db.stock_history.find({'partno': 'TE0004'}))
            self.assertEqual(1, len(history))
            entry = history[0]
            self.assertEqual('new in stock', entry.get('message'))
            self.assertEqual(23, entry.get('quantity'))

    def test_update_bom(self):
        self.login('viewer')
        rv = self.client.get('/stock/update-bom')
        self.assertEqual(302, rv.status_code)
        self.assertIn('/login', rv.location)
        self.logout()
        self.login('admin')
        rv = self.client.get('/stock/update-bom')
        self.assertEqual(200, rv.status_code)
        rv = self.client.post('/stock/update-bom', data=dict(
            file=open('testsuite/files/stock_bom.xlsx', 'rb')
        ))
        self.assertEqual(200, rv.status_code)
        start = rv.data.find(b'lpm_tmp_')
        end = rv.data.find(b'"', start)
        filename = rv.data[start:end]
        rv = self.client.post('/stock/update-bom', data=dict(
            tmpname=filename.decode('utf-8')
        ))
        self.assertEqual(302, rv.status_code)
        with self.app.app_context():
            obj = self.app.mongo.db.stock.find_one('TE0002')
            self.assertIsNotNone(obj)
            bom = obj.get('bom')
            refbom = [
                {'partno': 'TE0001', 'quantity': 1},
                {'partno': 'TE0004', 'quantity': 2},
            ]
            self.assertEqual(refbom, bom)


