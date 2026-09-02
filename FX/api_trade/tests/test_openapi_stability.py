from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient


class OpenApiStabilityTests(SimpleTestCase):
    def test_runtime_date_defaults_are_not_frozen_into_contract(self):
        response = APIClient().get(reverse("schema"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]

        for path in ("/api/get-calendar/", "/api/get-news/"):
            parameters = paths[path]["get"]["parameters"]
            date_parameters = {
                parameter["name"]: parameter
                for parameter in parameters
                if parameter["name"] in {"start", "end"}
            }
            for parameter in date_parameters.values():
                self.assertNotIn("default", parameter["schema"])
