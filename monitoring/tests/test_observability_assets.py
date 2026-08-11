import ast, json, pathlib, re, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

class ObservabilityAssetTests(unittest.TestCase):
    def test_dashboards_are_valid_json_without_secrets(self):
        files=list((ROOT/"monitoring/grafana").glob("beyvra-*.json")); self.assertEqual(len(files),5)
        for path in files:
            data=json.loads(path.read_text()); self.assertTrue(data["title"]); self.assertTrue(data["panels"])
            text=path.read_text().lower(); self.assertNotRegex(text,r"password|api[_-]?key|authorization|jwt|private[_-]?key")
    def test_metric_names_are_canonical_and_labels_bounded(self):
        text=(ROOT/"FX/apps/foundation/observability.py").read_text()
        names=set(re.findall(r'["\'](beyvra_[a-z0-9_]+)["\']',text)); self.assertGreaterEqual(len(names),45)
        forbidden={"user_id","order_id","trade_id","request_id","correlation_id","email","account_id","container_id","pid","url","channel"}
        tree=ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node,(ast.Call,)):
                for arg in node.args[2:]:
                    if isinstance(arg,(ast.Tuple,ast.List)):
                        labels={x.value for x in arg.elts if isinstance(x,ast.Constant) and isinstance(x.value,str)}
                        self.assertFalse(labels & forbidden)
    def test_alerts_have_severity_runbook_and_sustained_noisy_conditions(self):
        text=(ROOT/"monitoring/prometheus/beyvra-alerts.yml").read_text()
        alerts=re.split(r"\n  - alert: ",text)[1:]; self.assertGreaterEqual(len(alerts),10)
        for alert in alerts:
            self.assertRegex(alert,r"severity: (info|warning|critical)"); self.assertIn("runbook:",alert)
        self.assertNotIn('status_class=~"4',text)
    def test_public_proxy_does_not_expose_internal_monitoring(self):
        nginx=(ROOT/"nginx/nginx.prod.conf.template").read_text().lower()
        for path in ("/metrics","/prometheus/","/grafana/"):
            self.assertRegex(nginx,rf"location[^{{]*{re.escape(path)}[^{{]*{{\s*return 404;")
    def test_health_response_has_no_topology_or_secrets(self):
        text=(ROOT/"FX/apps/foundation/health.py").read_text().lower()
        self.assertNotRegex(text,r"\b(password|token|credential|hostname|port)\b")
        self.assertIn('def live(',text); self.assertIn('def ready(',text)

if __name__=="__main__": unittest.main()
