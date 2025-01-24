from django.test import TestCase
from rest_framework.test import APITestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from users.models import User
from .models import Transaction, Revenue, UserActivity, Trade
from datetime import datetime
from django.utils import timezone
import json

class DashboardMetricsTestCase(APITestCase):

    def setUp(self):
        self.dashboard_metrics_url = reverse("dashboard_metrics")
        tz = timezone.get_current_timezone()
    
        user1_data = {
            "first_name": 'Ronald',
            "last_name": 'Wall',
            "email": 'somerandom@somerandommail.com',
            "phone_number": '+999999999',
            "password": "testpass123",
        }
        user2_data = {
            "first_name": 'Sarah',
            "last_name": 'Stone',
            "email": 'another55@anothermail.com',
            "phone_number": '+888888888',
        }

        # Adding users        
        user1 = User.objects.create(**user1_data)
        user2 = User.objects.create(**user2_data)

        # Create test user
        test_user_details = {
            "email": "test@example.com",
            "password": "testpass123",
            "first_name": "Test",
            "last_name": "Test Name",
            "phone_number": "123456789123",
        }
        get_user_model().objects.create_user(**test_user_details)
        # Get token for authentication which will be used by tests
        payload = {
            "email": test_user_details["email"],
            "password": test_user_details["password"],
        }
        res = self.client.post(reverse("user:token_obtain_pair"), payload, HTTP_USER_AGENT='python-requests/2.31.0', REMOTE_ADDR='127.0.0.1')
        self.access_token = res.data['access']
        
        # Adding transactions
        Transaction.objects.create(user=user1, amount=25.6, date=timezone.make_aware(datetime(2015, 4, 11, 14, 25, 28), tz), transaction_type='Buy', category='cat1')
        Transaction.objects.create(user=user2, amount=67.8, date=timezone.make_aware(datetime(2023, 8, 16, 9, 56, 42), tz), transaction_type='Sell', category='cat2')
        
        # Adding revenues
        Revenue.objects.create(date=timezone.make_aware(datetime(2017, 5, 9, 15, 37, 5), tz), amount=120)
        Revenue.objects.create(date=timezone.make_aware(datetime(2024, 10, 16, 12, 18, 44), tz), amount=231.15)
        
        # Adding users activities
        UserActivity.objects.create(user=user1, last_active=timezone.make_aware(datetime(2024, 11, 8, 12, 32, 10), tz), is_active=True)
        UserActivity.objects.create(user=user2, last_active=timezone.make_aware(datetime(2023, 7, 15, 16, 41, 36), tz), is_active=False)
        
        # Adding trades
        Trade.objects.create(user=user1, asset='stocks', trade_volume=507.64, trade_date=timezone.make_aware(datetime(2016, 6, 17, 10, 38, 19), tz))
        Trade.objects.create(user=user2, asset='bonds', trade_volume=101.15, trade_date=timezone.make_aware(datetime(2015, 3, 2, 12, 14, 43), tz))


    # Tests related with getting metrics using date range selection

    def test_metrics_with_date_range(self):
        payload = {'start_date': '2015-01-01', 'end_date': '2017-12-31'}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = {
                            "transactions": 25.6,
                            "revenue": 120,
                            "transaction_volumes": 1,
                            "user_activity": 1,
                            "total_trades": 2
                            }
        
        #self.assertTrue(response.status_code == 200 and response.json == expected_result, 'Returned not correct metrics for date range')
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(json.loads(response.content), expected_result, 'Returned not correct metrics for date range')

    def test_not_correct_start_date_range(self):
        payload = {'start_date': 'random_string'}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"start_date":["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]}'
        
        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation of date range param format is failed')

    
    # Tests related with getting metrics using categories filters
    
    def test_filters_for_all_fields(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                                'field': 'user',
                                                                'operator': '=',
                                                                'value': 1,
                                                            },
                                                            {
                                                                'field': 'amount',
                                                                'operator': '=',
                                                                'value': 25.6,
                                                            },
                                                            {
                                                                'field': 'date',
                                                                'operator': '=',
                                                                'value': '2015-04-11 14:25:28',
                                                            },
                                                            {
                                                                'field': 'transaction_type',
                                                                'operator': '=',
                                                                'value': 'Buy',
                                                            },
                                                            {
                                                                'field': 'category',
                                                                'operator': '=',
                                                                'value': 'cat1',
                                                            },
                                                        ]
                                            },
                                            {
                                                'name': 'revenues',
                                                'filters': [
                                                            {
                                                                'field': 'date',
                                                                'operator': '=',
                                                                'value': '2017-05-09 15:37:05',
                                                            },
                                                            {
                                                                'field': 'amount',
                                                                'operator': '=',
                                                                'value': 120,
                                                            },
                                                        ]
                                            },
                                            {
                                                'name': 'users_activities',
                                                'filters': [
                                                            {
                                                                'field': 'user',
                                                                'operator': '=',
                                                                'value': 1,
                                                            },
                                                            {
                                                                'field': 'last_active',
                                                                'operator': '=',
                                                                'value': '2024-11-08 12:32:10',
                                                            },
                                                            {
                                                                'field': 'is_active',
                                                                'operator': '=',
                                                                'value': True,
                                                            },
                                                        ]
                                            },
                                            {
                                                'name': 'trades',
                                                'filters': [
                                                            {
                                                                'field': 'user',
                                                                'operator': '=',
                                                                'value': 1,
                                                            },
                                                            {
                                                                'field': 'asset',
                                                                'operator': '=',
                                                                'value': 'stocks',
                                                            },
                                                            {
                                                                'field': 'trade_volume',
                                                                'operator': '=',
                                                                'value': 507.64,
                                                            },
                                                            {
                                                                'field': 'trade_date',
                                                                'operator': '=',
                                                                'value': '2016-06-17 10:38:19',
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = {
                            "transactions": 25.6,
                            "revenue": 120.0,
                            "transaction_volumes": 1,
                            "user_activity": 1,
                            "total_trades":1
                            }

        #self.assertTrue(response.status_code == 200 and response.content == expected_result, 'Returned metrics doesn\'t match with expected result')
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(json.loads(response.content), expected_result, 'Returned metrics doesn\'t match with expected result')

    def test_filters_with_specific_operators(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                                'field': 'amount',
                                                                'operator': '>',
                                                                'value': 11,
                                                            },
                                                        ]
                                            },
                                            {
                                                'name': 'revenues',
                                                'filters': [
                                                            {
                                                                'field': 'date',
                                                                'operator': '<=',
                                                                'value': '2017-05-09 15:37:05',
                                                            },
                                                        ]
                                            },
                                            {
                                                'name': 'trades',
                                                'filters': [
                                                            {
                                                                'field': 'asset',
                                                                'operator': 'like',
                                                                'value': 'stocks',
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = {
                            "transactions": 93.4,
                            "revenue": 120.0,
                            "transaction_volumes": 2,
                            "user_activity": 1,
                            "total_trades": 1
                            }

        #self.assertTrue(response.status_code == 200 and response.content == expected_result, 'Returned metrics doesn\'t match with expected result')
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(json.loads(response.content), expected_result, 'Returned metrics doesn\'t match with expected result')

    # Test related with checking if filters are empty
    
    def test_is_filters_of_category_empty(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': []
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["\\"filters\\" Array for category \\"transactions\\" is empty. It must contain at least 1 filter."]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "is filters of category empty" is failed')

    
    # Test cases of not correct format of json
    

    def test_missing_categories_property(self):
        filters_dict = {
                            'random_property1': 'something',
                            'random_property2': 'something',
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["JSON object must have property \\"categories\\"(type \\"Array\\")."]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "missing categories property" is failed')

    def test_not_correct_format_of_category(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'random_property1': 'something',
                                                'random_property2': 'something',
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["Each category must be object with properties \\"name\\"(type \\"String\\"), \\"filters\\"(type \\"Array\\")"]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "not correct format of category" is failed')


    def test_not_correct_format_of_filter(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                              'random_property1': 'something',
                                                              'random_property2': 'something',  
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["Each filter must be object with properties \\"field\\"(type \\"string\\"), \\"operator\\"(type \\"string\\"), \\"value\\""]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "not correct format of filter" is failed')

    
    # Test requests with invalid data
    

    def test_not_existing_category(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'random_name',
                                                'filters': [
                                                            {
                                                                'field': 'amount',
                                                                'operator': '>',
                                                                'value': 11,
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["There is no category with name \\"random_name\\""]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "not existing category" is failed')

    def test_not_existing_field_for_category(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                                'field': 'random_name',
                                                                'operator': '=',
                                                                'value': 'something',
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["Field \\"random_name\\" is not allowed for filtering category \\"transactions\\""]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "not existing field for category" is failed')

    def test_invalid_operator_for_field(self):
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                                'field': 'amount',
                                                                'operator': 'random_string',
                                                                'value': 50,
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["Filter operator \\"random_string\\" is not allowed for \\"decimal\\" field"]}'

        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "invalid operator for field" is failed')
    
    def test_invalid_type_of_value_for_field(self):
        
        
        filters_dict = {
                            'categories': [
                                            {
                                                'name': 'transactions',
                                                'filters': [
                                                            {
                                                                'field': 'amount',
                                                                'operator': '=',
                                                                'value': 'string_value',
                                                            },
                                                        ]
                                            },
                                        ]
                        }
        filters_for_test = json.dumps(filters_dict)
        payload = {'start_date': '2011-01-01', 'categories_filters': filters_for_test}
        
        response = self.client.post(self.dashboard_metrics_url, payload, HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        expected_result = b'{"categories_filters":["Type of value string_value doesn\'t match with \\"decimal\\""]}'
        
        self.assertTrue(response.status_code == 400 and response.content == expected_result, 'Validation "invalid type of value for field" is failed')
        
