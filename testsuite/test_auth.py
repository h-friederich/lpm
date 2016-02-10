from testsuite import TestCase
from lpm import auth


class AuthTest(TestCase):

    def test_get_users(self):

        with self.app.app_context():

            # data is returned in alphabetical order!
            users = auth.get_users_with_role('login')
            self.assertEqual(3, len(users))
            u = users[0]
            self.assertEqual('admin', u.id)
            self.assertEqual('Admin', u.name)
            self.assertTrue(u.has_role('request_login'))
            self.assertFalse(u.has_role('something'))
            self.assertTrue(u.has_role('component_edit'))
            self.assertTrue(u.has_role('component_admin'))
            self.assertTrue(u.is_active)
            u = users[1]
            self.assertEqual('viewer', u.id)
            self.assertEqual('Viewer', u.name)
            self.assertFalse(u.has_role('request_login'))
            self.assertFalse(u.has_role('component_edit'))
            self.assertFalse(u.has_role('component_admin'))
            u = users[2]

            ua = users[0]
            users2 = auth.get_users_with_role('request_login')
            self.assertEqual(2, len(users2))
            ub = users2[0]
            self.assertEqual(ua, ub)

            users3 = auth.get_users_with_role('test')
            self.assertEqual(0, len(users3))
