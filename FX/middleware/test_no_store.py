from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory
from .no_store import SensitiveResponseNoStoreMiddleware


class SensitiveCachePolicyTests(SimpleTestCase):
    def response(self, path, policy=None):
        response = HttpResponse("ok")
        if policy is not None:
            response["Cache-Control"] = policy
        return SensitiveResponseNoStoreMiddleware(lambda request: response)(RequestFactory().get(path))

    def test_explicit_release_no_store_is_preserved(self):
        self.assertEqual(self.response("/api/v1/system/version", "no-store")["Cache-Control"], "no-store")

    def test_existing_strong_policy_is_not_replaced(self):
        policy = "private, no-store, no-cache, must-revalidate"
        self.assertEqual(self.response("/api/v1/watchlists", policy)["Cache-Control"], policy)

    def test_public_cache_permission_is_removed(self):
        response = self.response("/api/v1/portfolio/summary", "public, max-age=300")
        directives = {item.strip() for item in response["Cache-Control"].split(",")}
        self.assertNotIn("public", directives)
        self.assertTrue({"private", "no-store"}.issubset(directives))

    def test_missing_sensitive_policy_is_added(self):
        response = self.response("/api/v1/watchlists")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["Pragma"], "no-cache")

    def test_static_cache_is_not_changed(self):
        self.assertEqual(self.response("/static/app.js", "public, max-age=3600")["Cache-Control"], "public, max-age=3600")
