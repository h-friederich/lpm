from testsuite import TestCase
from lpm import login


class LoginTest(TestCase):

    def test_login_logout(self):
        rv = self.login('admin', '1234')
        self.assertIn(b'Logged in as: Admin', rv.data)
        rv = self.client.get('/items/')
        rv = self.logout()
        self.assertIn(b'for="username"', rv.data)  # login page
        rv = self.login('adminx', '1234')
        self.assertIn(b'invalid credentials', rv.data)
        rv = self.login('admin', '12345')
        self.assertIn(b'invalid credentials', rv.data)
        rv = self.login('adminx', '12345')
        self.assertIn(b'invalid credentials', rv.data)
        rv = self.login('disabled', '1234')
        self.assertIn(b'login expired', rv.data)
        rv = self.login('ext', '1234')
        self.assertIn(b'insufficient permissions', rv.data)

