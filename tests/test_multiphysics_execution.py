"""C adapter regressions with explicit solver doubles; never physical evidence."""
import copy
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from test_core import temporary_workspace, cleanup_workspace, config, completed, FakeRuntime
from dcac_agent.multiphysics import execute_multiphysics, field_options, write_json
from dcac_agent.contracts import read_multiphysics
from dcac_agent.agent import AgentService
from dcac_agent.store import Store


class FieldAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace(); self.root = Path(self.temp.name)
        self.run = dict(id='bbbbbbbbbbbb', revision=1, status='completed', action='simulate', spec={'test_fixture':1})
        self.session = dict(id='aaaaaaaaaaaa', revision=1, spec=self.run['spec'])
        self.folder = self.root / 'parent'; self.folder.mkdir()
        # Synthetic parent metadata used only for adapter contract tests.
        self.parent = dict(ok=True, source='MATLAB/Simulink', action='simulate', spec=self.run['spec'],
                           run_context=dict(session_id=self.session['id'], run_id=self.run['id'], design_revision=1))
        write_json(self.folder/'result.json', self.parent)
        (self.folder/'electrical_raw_v1.mat').write_bytes(b'TEST_DOUBLE_NOT_A_MAT_FILE')
        self.result = dict(ok=True, status='completed', schema_version='1.0', session_id=self.session['id'],
            parent_run_id=self.run['id'], revision=1, evidence='test', component_version='TEST', material_version='TEST',
            boundary_version='TEST', solver='TEST_DOUBLE', verification={'test_only':True},
            domains={d:dict(status='completed', metrics={'test_metric':dict(value=1,unit='test')}, artifacts=['test.json']) for d in ['magnetic','thermal','structural']})

    def tearDown(self):
        cleanup_workspace(self.temp)

    def runtime(self, failure=None):
        outer=self
        class Double:
            def execute_fields(self,out,cancel,emit):
                if failure: raise failure
                (out/'test.json').write_text('{}')
                return copy.deepcopy(outer.result)
        return Double()

    def execute(self, runtime=None, cancel=None):
        return execute_multiphysics(runtime or self.runtime(), self.folder,self.session,self.run,cancel or threading.Event(),lambda *a:None)

    def test_success_links_attempt_and_preserves_parent(self):
        original=(self.folder/'result.json').read_bytes()
        result=self.execute()
        self.assertEqual(result['evidence'],'test')
        self.assertIn('/fields/',result['domains']['magnetic']['files'][0]['url'])
        self.assertEqual((self.folder/'result.json').read_bytes(),original)
        self.assertEqual(json.loads((self.folder/'multiphysics_status.json').read_text())['status'],'completed')
        self.assertEqual(set(result['source_sha256']),{'result.json','electrical_raw_v1.mat'})
        reloaded=read_multiphysics(self.folder,self.session,self.run)
        self.assertEqual(reloaded['attempt_id'],result['attempt_id'])

    def test_stale_cross_run_and_test_parent_rejected(self):
        self.session['revision']=2
        with self.assertRaises(ValueError): self.execute()
        self.session['revision']=1
        self.parent['run_context']['run_id']='wrong';write_json(self.folder/'result.json',self.parent)
        with self.assertRaises(ValueError): self.execute()
        self.parent['run_context']['run_id']=self.run['id'];self.parent['source']='TEST_DOUBLE_ONLY'
        write_json(self.folder/'result.json',self.parent)
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse((self.folder/'fields').exists())

    def test_failed_attempt_does_not_show_previous_success(self):
        self.execute(); previous=(self.folder/'multiphysics_result.json').read_bytes()
        with self.assertRaises(RuntimeError): self.execute(self.runtime(RuntimeError('solver failed')))
        self.assertEqual(read_multiphysics(self.folder,self.session,self.run)['status'],'failed')
        self.assertEqual((self.folder/'multiphysics_result.json').read_bytes(),previous)

    def test_cancelled_attempt(self):
        with self.assertRaises(InterruptedError): self.execute(self.runtime(InterruptedError('cancelled')))
        self.assertEqual(read_multiphysics(self.folder,self.session,self.run)['status'],'cancelled')
        self.assertFalse((self.folder/'multiphysics_result.json').exists())

    def test_boundaries_and_invalid_output(self):
        for options in [dict(core_heat_w=-1),dict(ambient_c=float('nan')),dict(convection_w_m2k=True),dict(shell='bad')]:
            with self.assertRaises(ValueError): field_options(options)
        self.result['domains']['thermal']['artifacts']=['../outside.json']
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(read_multiphysics(self.folder,self.session,self.run)['status'],'failed')

    def test_agent_automatically_runs_missing_electrical(self):
        store=Store(self.root/'store');sid=store.create()['id']
        service=AgentService(config(),store,FakeRuntime())
        try:
            with patch('dcac_agent.agent.OUTPUTS',self.root/'outputs'), patch('dcac_agent.agent.execute_multiphysics',return_value=self.result) as solver:
                # Exercise tool orchestration without a physical solver or user data.
                job={'session_id':sid,'cancel':threading.Event(),'events':[]}
                service._tool(job,'run_multiphysics',{})
                row=store.snapshot(sid)
                self.assertEqual(row['runs'][-1]['action'],'simulate')
                self.assertEqual(solver.call_args.args[3]['id'],row['runs'][-1]['id'])
                self.assertTrue(any(e['title']=='run_simulation' for e in job['events']))
        finally:service.pool.shutdown(wait=True)
