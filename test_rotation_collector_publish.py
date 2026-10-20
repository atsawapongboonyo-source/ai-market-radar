from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from capital_rotation_automation import run_once, write_json
from rotation_collector_publish import publish_once, STAGING_ENDPOINT
from test_capital_rotation_automation import snapshot_for


class CollectorPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026,10,20,12,tzinfo=timezone.utc)
        run_once(self.root, now=self.now, fetcher=lambda **kw:snapshot_for(kw['expected_session']))
        write_json(self.root/'publisher.json', {'enabled':True, 'endpoint':STAGING_ENDPOINT})
        self.sender = Mock(return_value=200)
        self.loader = Mock(return_value=object())

    def run_publish(self, **kwargs):
        return publish_once(self.root, now=kwargs.pop('now',self.now), sender=self.sender,
                            key_loader=self.loader, **kwargs)

    def test_only_public_projection_is_sent_and_outbox_is_durable(self):
        result = self.run_publish()
        self.assertEqual(result['status'],'PUBLISHED')
        raw = self.sender.call_args.args[1]
        value = json.loads(raw)
        self.assertEqual(set(value),{'schema_version','session_date','generated_utc','feed','returns'})
        self.assertEqual(len(value['returns']['20d']),14)
        self.assertEqual(raw,(self.root/'public-outbox'/'2026-10-19.json').read_bytes())
        self.assertNotIn('calculation_audit',raw.decode())

    def test_same_session_is_republished_to_recover_empty_server(self):
        self.run_publish(); self.run_publish()
        self.assertEqual(self.sender.call_count,2)
        self.assertEqual(len(list((self.root/'public-outbox').glob('*.json'))),1)

    def test_tampered_evidence_never_reaches_network_or_key(self):
        path=self.root/'daily'/'2026-10-19.json'
        value=json.loads(path.read_text());value['observations']['SPY'][0]['close']=1234
        write_json(path,value)
        self.assertEqual(self.run_publish()['status'],'BLOCKED')
        self.sender.assert_not_called(); self.loader.assert_not_called()

    def test_stale_health_and_blocked_collector_never_publish(self):
        self.assertEqual(self.run_publish(now=self.now+timedelta(minutes=31))['status'],'BLOCKED')
        write_json(self.root/'health.json',{'status':'BLOCKED'})
        self.assertEqual(self.run_publish()['status'],'BLOCKED')
        self.sender.assert_not_called()

    def test_changed_endpoint_disabled_config_and_failure_are_safe(self):
        write_json(self.root/'publisher.json',{'enabled':True,'endpoint':'https://other.example/api/rotation/ingest'})
        self.assertEqual(self.run_publish()['error_code'],'PUBLISHER_NOT_CONFIGURED')
        self.sender.assert_not_called()
        write_json(self.root/'publisher.json',{'enabled':True,'endpoint':STAGING_ENDPOINT})
        self.sender.side_effect=RuntimeError('SECRET_SENTINEL')
        result=self.run_publish()
        self.assertEqual(result['error_code'],'PUBLISHER_UNAVAILABLE')
        self.assertNotIn('SECRET_SENTINEL',(self.root/'publication-health.json').read_text())


if __name__=='__main__': unittest.main()
