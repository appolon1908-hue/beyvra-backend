from datetime import datetime, timezone
from decimal import Decimal
from django.test import TestCase
from .market_authority import EventEnvelope, Provenance, Quote, TradeTick
from .market_store import persist_event
from .models import CanonicalQuote, CanonicalTradeTick


class MarketStoreTests(TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc); self.provenance=Provenance("fixture","trade",self.now,self.now,"WEBSOCKET",raw_message_hash="hash")
    def test_quote_and_trade_persistence_is_idempotent_and_raw_payload_free(self):
        quote=Quote("BTC-USD",Decimal("1"),Decimal("2"),None,None,None,self.now,self.now,"fixture","1",False,False,self.provenance)
        trade=TradeTick("BTC-USD",Decimal("1.5"),Decimal("2"),"opaque",self.now,self.now,"fixture","FIXTURE","2",(),self.provenance)
        persist_event(quote); persist_event(quote); persist_event(trade); persist_event(trade)
        self.assertEqual(CanonicalQuote.objects.count(),1); self.assertEqual(CanonicalTradeTick.objects.count(),1)
        self.assertNotIn("raw_payload",CanonicalTradeTick.objects.get().provenance)
