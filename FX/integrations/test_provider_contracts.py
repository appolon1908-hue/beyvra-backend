from django.test import SimpleTestCase

from integrations.provider_contracts import ExecutionRouter, ProviderMode, RoutingDecision


class ExecutionRouterTests(SimpleTestCase):
    def setUp(self):
        self.router = ExecutionRouter()

    def route(self, **overrides):
        values = {"simulation_authorized": True, "incident_active": False, "market_data_fresh": True, "requested_mode": ProviderMode.SIMULATION}
        values.update(overrides)
        return self.router.route(**values)

    def test_only_simulation_can_route(self):
        self.assertEqual(self.route(), RoutingDecision.SIMULATION)
        self.assertEqual(self.route(requested_mode=ProviderMode.PAPER), RoutingDecision.DENIED)
        self.assertEqual(self.route(requested_mode=ProviderMode.LIVE), RoutingDecision.DENIED)

    def test_safety_preconditions_fail_closed(self):
        self.assertEqual(self.route(simulation_authorized=False), RoutingDecision.DENIED)
        self.assertEqual(self.route(incident_active=True), RoutingDecision.DENIED)
        self.assertEqual(self.route(market_data_fresh=False), RoutingDecision.DENIED)

