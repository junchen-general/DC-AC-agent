import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from dcac_agent.store import Store
from dcac_agent.design import DesignSpec
from dcac_agent.multiphysics import digest
from dcac_agent.candidate_revision import apply_candidate_revision


class CandidateRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'store')
        self.sid=self.store.create()['id']
        self.rid='a'*12
        self.folder=self.root/'outputs'/self.sid/self.rid
        self.folder.mkdir(parents=True)
        self.run=dict(id=self.rid,revision=0,spec=DesignSpec().to_dict(),status='completed',action='simulate')
        self.store.add_run(self.sid,self.run)
        (self.folder/'result.json').write_text('{}')
        (self.folder/'electrical_raw_v1.mat').write_bytes(b'fixture only')
        self.fields=dict(status='completed',evidence='numerical',stale=False,session_id=self.sid,
            parent_run_id=self.rid,revision=0,attempt_id='b'*12,component_version='E70-test',
            source_sha256={p:digest(self.folder/p) for p in ['result.json','electrical_raw_v1.mat']},
            input_summary=dict(candidate_L_H=.00190904321987,candidate_R20_ohm=.21664071234),
            domains={k:dict(status='completed') for k in ['magnetic','thermal','structural']})
        self.write()

    def tearDown(self): self.tmp.cleanup()

    def write(self):
        (self.folder/'multiphysics_result.json').write_text(json.dumps(self.fields))

    def apply(self):
        with patch('dcac_agent.candidate_revision.read_multiphysics',return_value=copy.deepcopy(self.fields)):
            return apply_candidate_revision(self.store,self.root/'outputs',self.sid,self.rid)

    def test_exact_parameters_new_revision_and_preserved_history(self):
        result=self.apply(); current=self.store.snapshot(self.sid)
        self.assertEqual(current['revision'],1)
        self.assertEqual(current['spec']['inductance'],self.fields['input_summary']['candidate_L_H'])
        self.assertEqual(current['spec']['winding_resistance'],self.fields['input_summary']['candidate_R20_ohm'])
        self.assertEqual(current['runs'][0],self.run)
        self.assertEqual(result['candidate_update']['resistance_reference_temperature_c'],20)
        self.assertEqual(current['candidate_updates'][0]['source_run_id'],self.rid)
        self.assertEqual(Store(self.root/'store').snapshot(self.sid)['revision'],1)

    def test_stale_rejected_without_update(self):
        self.store.update_spec(self.sid,{'capacitance':5e-6})
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.store.snapshot(self.sid)['revision'],1)

    def test_source_tampering_rejected(self):
        (self.folder/'electrical_raw_v1.mat').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.store.snapshot(self.sid)['revision'],0)

    def test_invalid_candidate_or_evidence_rejected(self):
        for value in [float('nan'),True,-1,100]:
            self.fields['input_summary']['candidate_L_H']=value
            self.write()
            with self.assertRaises(ValueError): self.apply()
        self.fields['input_summary']['candidate_L_H']=.0019
        self.fields['evidence']='test';self.write()
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.store.snapshot(self.sid)['revision'],0)

    def test_missing_or_cross_session_rejected(self):
        self.fields['session_id']='c'*12;self.write()
        with self.assertRaises(ValueError): self.apply()
        with self.assertRaises(ValueError):
            apply_candidate_revision(self.store,self.root/'outputs',self.sid,'../bad')

    def test_agent_dispatches_explicit_candidate_tool(self):
        from dcac_agent.agent import AgentService,TOOLS
        from test_core import config,FakeRuntime
        self.assertIn('apply_candidate_parameters',[t['function']['name'] for t in TOOLS])
        service=AgentService(config(),self.store,FakeRuntime())
        job=dict(session_id=self.sid,cancel=threading.Event(),events=[])
        try:
            with patch('dcac_agent.agent.OUTPUTS',self.root/'outputs'), patch(
                    'dcac_agent.candidate_revision.read_multiphysics',return_value=copy.deepcopy(self.fields)):
                result=service._tool(job,'apply_candidate_parameters',{'run_id':self.rid})
            self.assertEqual(result['revision'],1)
        finally: service.pool.shutdown(wait=True)

    def test_failure_to_save_rolls_back_revision(self):
        with patch.object(self.store,'save',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.apply()
        self.assertEqual(self.store.snapshot(self.sid)['revision'],0)

    def test_rules_do_not_apply_when_asked_for_explanation(self):
        from dcac_agent.agent import AgentService
        from test_core import config,FakeRuntime
        service=AgentService(config(),self.store,FakeRuntime())
        job=dict(session_id=self.sid,cancel=threading.Event(),events=[])
        try:
            for text in ('解释一下回填候选参数', '不要应用候选电感'):
                service._rules(job,text)
                self.assertEqual(self.store.snapshot(self.sid)['revision'],0)
            with patch('dcac_agent.agent.OUTPUTS',self.root/'outputs'), patch(
                    'dcac_agent.candidate_revision.read_multiphysics',return_value=copy.deepcopy(self.fields)):
                service._rules(job,'回填候选参数')
            self.assertEqual(self.store.snapshot(self.sid)['revision'],1)
        finally: service.pool.shutdown(wait=True)

    def test_step_check_preserves_original_thresholds(self):
        from tools.run_lr_iteration import compare
        fine=dict(output_rms=220,inductor_rms=2,inductor_peak=4,thd_percent=.1)
        coarse={**fine,'inductor_peak':4.05}
        self.assertFalse(compare(coarse,fine)['converged'])
        coarse={**fine,'inductor_peak':4.01}
        self.assertTrue(compare(coarse,fine)['converged'])
