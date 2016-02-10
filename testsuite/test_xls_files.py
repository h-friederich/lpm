import os
from io import BytesIO
from flask import Flask, request
from testsuite import TestCase
import lpm.xls_files


class XlsFilesTest(TestCase):

    def test_save(self):

        # temporarily register a new method to test the file functionality
        @self.app.route('/testupload', methods=['POST'])
        def upload():
            form = lpm.xls_files.FileForm(request.form)
            lpm.xls_files.save_to_tmp(form)
            return form.tmpname.data

        rv = self.client.post('/testupload', data=dict(
            file=(BytesIO(b'123456\n789'), 'upload.txt')
        ))
        filename = rv.data.decode('utf-8')
        filepath = os.path.join('/tmp/', filename)
        self.assertTrue(os.path.exists(filepath))
        with open(filepath, 'rb') as f:
            self.assertEqual(b'123456\n789', f.read())

        with self.app.app_context():
            form = lpm.xls_files.FileForm()
            form.tmpname.data = filename
            self.assertEqual(filepath, lpm.xls_files.extract_filepath(form))

    def test_file_read(self):
        with self.assertRaises(ValueError, msg='only single-sheet workbooks supported'):
            lpm.xls_files.read_xls('testsuite/files/twosheets.xlsx')

        headers, data = lpm.xls_files.read_xls('testsuite/files/good.xlsx')
        ref = [
            {'serial': 'LPM0001', 'partno': 'LP0001a', 'batch': 'b1', 'param': 'qwer'},
            {'serial': 'LPM0002', 'partno': 'LP0001a', 'batch': 'b1'},
            {'serial': 'LPM0003', 'partno': 'LP0001a', 'batch': 'b1', 'comment': 'some comment here'},
            {'serial': 'LPM0004', 'partno': 'LP0002b', 'batch': 'b2'},
        ]
        self.assertEqual(['serial', 'partno', 'batch', 'param', 'comment'], headers)
        self.assertEqual(ref, data)

        # parsing stops at the first empty column
        headers, data = lpm.xls_files.read_xls('testsuite/files/nokey.xlsx')
        ref = [
            {'serial': 'LP0001', 'partno': 'LPM0001a'},
            {'serial': 'LP0002', 'partno': 'LPM0001a'},
            {'serial': 'LP0003', 'partno': 'LPM0003a'},
        ]
        self.assertEqual(['serial', 'partno'], headers)
        self.assertEqual(ref, data)
