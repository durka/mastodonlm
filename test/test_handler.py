"""Tests for lambda handler"""

import json
import logging
from unittest.mock import MagicMock, patch, sentinel
from unittest import TestCase
from mastodon import MastodonAPIError, MastodonUnauthorizedError
import handler

# Here, reconfigure the logger to send output to a file during tests.
logging.basicConfig(level=logging.INFO, filename="debug_log.txt")


def mock_userdict(username):
    """Returns a mock user dict"""
    return {
        "id": username,
        "display_name": f"dn-{username}",
        "username": f"{username}",
        "acct": f"act-{username}",
        "note": f"note-{username}",
        "avatar": f"avatar-{username}",
        "following_count": 100,
    }


def mock_listdict(listid):
    """Returns a mock list dict"""
    return {"id": listid, "title": f"title-{listid}"}


def mock_mastodon():
    """Returns a mock fo the Mastodon object"""
    res = MagicMock()
    res.auth_request_url.return_value = "https://mock_redirect"
    res.lists.return_value = [mock_listdict("listid1")]
    res.me.return_value = mock_userdict("me")
    return res


def mock_factory():
    """Returns a mock Mastondon Factory with reasonsable defaults"""

    factory = MagicMock()
    mastodon = mock_mastodon()
    factory.from_config.return_value = mastodon
    factory.from_cookie.return_value = mastodon
    return factory


def setupNoCookies():
    """Returns event and context objects for tests with no cookies"""

    event = {"headers": {"origin": "none"}}
    context = {}

    return (event, context)


def setupWithCookies():
    """Returns event and context objects for tests with with a cookie"""

    event = {
        "headers": {"origin": "none", "authorization": "mycookie"},
    }
    context = {}

    return (event, context)


class TestAuth(TestCase):
    """Tests for /auth methods"""

    def test_auth_nodomain(self):
        """Test /auth with no domain parameter - there's little we can do!"""
        (event, context) = setupNoCookies()

        res = handler.auth(event, context)
        # We should return a 401 response
        self.assertEqual(res["statusCode"], 401)
        self.assertEqual(json.loads(res["body"])["status"], "no_login")

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_nocookie_newhost(self, make_app, _factory, dataStore):
        """Test /auth when we haven't seen this host before"""

        (event, context) = setupNoCookies()
        event["queryStringParameters"] = {"domain": "mydomain"}

        dataStore.is_allowed.return_value = True
        dataStore.get_host_config.return_value = None
        make_app.return_value = ("id", "secret")

        res = handler.auth(event, context)
        # We should return a 200 response with the correct redirect URL.
        # And, we should call make_app
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["url"], "https://mock_redirect")
        # We should have created a new mastodon app
        self.assertTrue(make_app.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_nocookie_knownhost(self, make_app, factory, dataStore):
        """Test /auth when no cookie is present"""

        (event, context) = setupNoCookies()
        event["queryStringParameters"] = {"domain": "mydomain"}

        dataStore.is_allowed.return_value = True
        dataStore.get_host_config.return_value = sentinel.host_cfg

        res = handler.auth(event, context)
        # We should return a 200 response with the correct redirect URL.
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["url"], "https://mock_redirect")
        # We should have made a mastodon instance from the stored config
        self.assertTrue(factory.from_config.called_with(sentinel.host_cfg))
        # We should not have created a new app
        self.assertFalse(make_app.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_cookie_valid(self, make_app, factory, data_store):
        """Test /auth when a cookie present and a valid session on a Mastodon server"""

        (event, context) = setupWithCookies()

        data_store.is_allowed.return_value = True
        auth = MagicMock()
        auth.domain = "mydomain"
        data_store.get_auth.return_value = auth

        res = handler.auth(event, context)
        # We should return a 200 response
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["status"], "OK")
        # We should have made a mastodon instance from the stored config
        self.assertTrue(factory.from_cookie.called_with("mycookie"))
        # We should not have created a new app
        self.assertFalse(make_app.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_cookie_unknown(self, make_app, factory, data_store):
        """Test /auth when a cookie present but it is unknown to us"""

        (event, context) = setupWithCookies()

        # Make the me() method throw, which is how we know we aren't logged in.
        factory.from_cookie.return_value.me.side_effect = handler.NoAuthInfo

        data_store.is_allowed.return_value = True

        res = handler.auth(event, context)
        # We should return a 200 response with the correct redirect URL.
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["url"], "https://mock_redirect")
        # We should have made a mastodon instance from the stored config
        self.assertTrue(factory.from_cookie.called_with("mycookie"))
        # We should not have created a new app
        self.assertFalse(make_app.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_cookie_invalid(self, make_app, factory, data_store):
        """Test /auth when a cookie present and an invalid session on a Mastodon
        server"""

        (event, context) = setupWithCookies()

        # Make the me() method throw, which is how we know we aren't logged in.
        factory.from_cookie.return_value.me.side_effect = MastodonAPIError

        data_store.is_allowed.return_value = True
        auth = MagicMock()
        auth.domain = "mydomain"
        data_store.get_auth.return_value = auth

        res = handler.auth(event, context)
        # We should return a 200 response with the correct redirect URL.
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["url"], "https://mock_redirect")
        # We should have made a mastodon instance from the stored config
        self.assertTrue(factory.from_cookie.called_with("mycookie"))
        # We should not have created a new app
        self.assertFalse(make_app.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    @patch("handler.make_app")
    def test_auth_cookie_valid_no_hostmatch(self, make_app, factory, data_store):
        """Test /auth when a cookie present but the domain doesn't match the one
        in the cookie"""

        (event, context) = setupNoCookies()
        event["queryStringParameters"] = {"domain": "anotherdomain"}

        data_store.is_allowed.return_value = True
        auth = MagicMock()
        auth.domain = "mydomain"
        data_store.get_auth.return_value = auth

        res = handler.auth(event, context)
        # We should return a 200 response with the correct redirect URL.
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"])["url"], "https://mock_redirect")
        # We should have made a mastodon instance from the stored config
        self.assertTrue(factory.from_cookie.called_with("mycookie"))
        # We should not have created a new app
        self.assertFalse(make_app.called)


class TestInfo(TestCase):
    """Tests for /meta, /following, /lists methods"""

    def helper_nocookie(self, method):
        """Test for several methods when a cookie is not present"""

        (event, context) = setupNoCookies()

        res = method(event, context)

        # We should return a 403 response with the correct status info
        self.assertEqual(res["statusCode"], 403)
        self.assertEqual(json.loads(res["body"])["status"], "no_cookie")

    def test_meta_nocookie(self):
        """Test /meta when a cookie is not present"""

        self.helper_nocookie(handler.meta)

    def test_following_nocookie(self):
        """Test /following when a cookie is not present"""

        self.helper_nocookie(handler.following)

    def test_lists_nocookie(self):
        """Test /lists when a cookie is not present"""

        self.helper_nocookie(handler.lists)

    def helper_unknowncookie(self, factory, func):
        """Test /meta when cookie is present but mastodon API throws an error"""

        (event, context) = setupWithCookies()

        # We use Mastodon.me() to ensure someone has logged in.
        factory.from_cookie.return_value.me.side_effect = handler.NoAuthInfo

        res = func(event, context)

        # We should return a 403 response with the correct status info
        self.assertEqual(res["statusCode"], 403)
        self.assertEqual(json.loads(res["body"])["status"], "no_cookie")

    def helper_badcookie(self, factory, func):
        """Test /meta when cookie is present but mastodon API throws an error"""

        (event, context) = setupWithCookies()

        # We use Mastodon.me() to ensure someone has logged in.
        factory.from_cookie.return_value.me.side_effect = MastodonUnauthorizedError

        res = func(event, context)

        # We should return a 403 response with the correct status info
        self.assertEqual(res["statusCode"], 403)
        self.assertEqual(json.loads(res["body"])["status"], "no_cookie")

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_meta_badcookie(self, factory):
        """Test /meta when a bad cookie is present"""

        self.helper_badcookie(factory, handler.meta)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_meta_unknowncookie(self, factory):
        """Test /meta when a bad cookie is present"""

        self.helper_unknowncookie(factory, handler.meta)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_following_badcookie(self, factory):
        """Test /following when a bad cookie is present"""

        self.helper_badcookie(factory, handler.following)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_following_unknowncookie(self, factory):
        """Test /following when a bad cookie is present"""

        self.helper_unknowncookie(factory, handler.following)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_lists_badcookie(self, factory):
        """Test /lists when a bad cookie is present"""

        self.helper_badcookie(factory, handler.lists)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_lists_unknowncookie(self, factory):
        """Test /lists when a bad cookie is present"""

        self.helper_unknowncookie(factory, handler.lists)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_following(self, factory, data_store):
        """Test /following"""

        (event, context) = setupWithCookies()

        auth = MagicMock()
        auth.domain = "mydomain"
        data_store.get_auth.return_value = auth
        mastomock = factory.from_cookie.return_value
        mastomock.account_following.return_value = sentinel.account_following

        res = handler.following(event, context)

        mastomock.fetch_remaining.assert_called_with(sentinel.account_following)
        self.assertEqual(res["statusCode"], 200)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_lists(self, factory, data_store):
        """Test /lists"""

        (event, context) = setupWithCookies()

        auth = MagicMock()
        auth.domain = "mydomain"
        data_store.get_auth.return_value = auth
        mastomock = factory.from_cookie.return_value
        mastomock.list_accounts.return_value = sentinel.list_accounts

        res = handler.lists(event, context)

        mastomock.fetch_remaining.assert_called_with(sentinel.list_accounts)
        self.assertEqual(res["statusCode"], 200)


class TestCRUD(TestCase):
    """Tests for /create, /delete, /add, /remove methods"""

    def helper_no_cookie(self, func):
        """Helper function for no cookie test cases"""
        (event, context) = setupNoCookies()

        res = func(event, context)
        # We should return a 403 response with the correct status info
        self.assertEqual(res["statusCode"], 403)
        self.assertEqual(json.loads(res["body"])["status"], "no_cookie")

    def helper_badcookie(self, factory, func):
        """Test /info when cookie is present but mastodon API throws an error"""

        (event, context) = setupWithCookies()

        # We use Mastodon.me() to ensure someone has logged in.
        factory.from_cookie.return_value.me.side_effect = MastodonUnauthorizedError

        res = func(event, context)

        # We should return a 403 response with the correct status info
        self.assertEqual(res["statusCode"], 403)
        self.assertEqual(json.loads(res["body"])["status"], "not_authorized")

    def test_create_no_cookie(self):
        """Test /create with no cookie"""

        self.helper_no_cookie(handler.create_list)

    def test_delete_no_cookie(self):
        """Test /delete with no cookie"""

        self.helper_no_cookie(handler.delete_list)

    def test_add_no_cookie(self):
        """Test /add with no cookie"""

        self.helper_no_cookie(handler.add_to_list)

    def test_remove_no_cookie(self):
        """Test /remove with no cookie"""

        self.helper_no_cookie(handler.remove_from_list)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_create_badcookie(self, factory):
        """Test /create with a bad cookie"""

        self.helper_badcookie(factory, handler.create_list)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_delete_badcookie(self, factory):
        """Test /create with a bad cookie"""

        self.helper_badcookie(factory, handler.delete_list)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_add_badcookie(self, factory):
        """Test /create with a bad cookie"""

        self.helper_badcookie(factory, handler.add_to_list)

    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_remove_badcookie(self, factory):
        """Test /create with a bad cookie"""

        self.helper_badcookie(factory, handler.remove_from_list)

    def helper_func(self, _factory, _data_store, query_params, func, mastofunc):
        """Test a CRUD function assuming good auth"""
        (event, context) = setupWithCookies()
        event["queryStringParameters"] = query_params

        res = func(event, context)

        self.assertEqual(res["statusCode"], 200)
        self.assertTrue(mastofunc.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_create(self, factory, data_store):
        """Test /create"""
        mf = factory.from_cookie.return_value.list_create
        qs = {"list_name": "listname"}
        self.helper_func(factory, data_store, qs, handler.create_list, mf)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_delete(self, factory, data_store):
        """Test /delete"""
        mf = factory.from_cookie.return_value.list_delete
        qs = {"list_id": "listid"}
        self.helper_func(factory, data_store, qs, handler.delete_list, mf)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_add(self, factory, data_store):
        """Test /add"""
        mf = factory.from_cookie.return_value.list_accounts_add
        qs = {"list_id": "listid", "account_id": "acctid"}
        self.helper_func(factory, data_store, qs, handler.add_to_list, mf)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_remove(self, factory, data_store):
        """Test /remove"""
        mf = factory.from_cookie.return_value.list_accounts_delete
        qs = {"list_id": "listid", "account_id": "acctid"}
        self.helper_func(factory, data_store, qs, handler.remove_from_list, mf)

    def helper_func_error(self, _factory, _data_store, query_params, func, mastofunc):
        """Test a CRUD function assuming good auth, but an error after"""
        (event, context) = setupWithCookies()
        event["queryStringParameters"] = query_params

        res = func(event, context)

        self.assertEqual(res["statusCode"], 500)
        self.assertTrue(mastofunc.called)

    @patch("handler.Datastore")
    @patch("handler.MastodonFactory", new_callable=mock_factory)
    def test_add_error(self, factory, data_store):
        """Test /add with errors"""
        mf = factory.from_cookie.return_value.list_accounts_add
        mf.side_effect = MastodonAPIError
        qs = {"list_id": "listid", "account_id": "acctid"}
        self.helper_func_error(factory, data_store, qs, handler.add_to_list, mf)
