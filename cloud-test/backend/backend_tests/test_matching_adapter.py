import copy
import json
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request as HttpRequest, urlopen

from fastapi import FastAPI, Request
import uvicorn
from matching_adapter import create_matching_router


class MatchingAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((Path(__file__).resolve().parents[1]/'vendor/RoleMesh_matching_v0_1/examples/input.json').read_text(encoding='utf-8'))
        cls.allow_profile=Mock(return_value=True)
        cls.allow_role=Mock(return_value=True)
        cls.profile_loader=Mock()
        cls.role_loader=Mock()
        cls.profiles_loader=Mock()
        cls.roles_loader=Mock()
        def principal(request: Request):
            # Synthetic test-only identity fixture, not a production auth design.
            return 'synthetic.user' if request.headers.get('Authorization')=='Bearer synthetic-test' else None
        cls.app=FastAPI()
        cls.app.include_router(create_matching_router(get_principal=principal,
            authorize_profile=cls.allow_profile,authorize_role=cls.allow_role,
            load_profile=cls.profile_loader,load_role=cls.role_loader,
            load_profiles=cls.profiles_loader,load_roles=cls.roles_loader,max_candidates=10))
        cls.sock=socket.socket()
        cls.sock.bind(('127.0.0.1',0))
        cls.base=f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server=uvicorn.Server(uvicorn.Config(cls.app,log_level='critical',access_log=False))
        cls.thread=threading.Thread(target=cls.server.run,kwargs={'sockets':[cls.sock]},daemon=True)
        cls.thread.start()
        deadline=time.monotonic()+10
        while not cls.server.started:
            if not cls.thread.is_alive() or time.monotonic()>deadline:
                raise RuntimeError('Adapter test server startup failed')
            time.sleep(.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit=True
        cls.thread.join(timeout=10)
        cls.sock.close()

    def setUp(self):
        self.allow_profile.reset_mock(return_value=True,side_effect=True)
        self.allow_role.reset_mock(return_value=True,side_effect=True)
        self.allow_profile.return_value=True
        self.allow_role.return_value=True
        for loader,value in [(self.profile_loader,self.data['profile']),(self.role_loader,self.data['roles'][0]),
                             (self.roles_loader,self.data['roles']),(self.profiles_loader,[self.data['profile']])]:
            loader.reset_mock(return_value=True,side_effect=True)
            loader.return_value=copy.deepcopy(value)

    def request(self,direction='projects',body=None,authenticated=True):
        body=body if body is not None else ({'profile_id':self.data['profile']['profile_id']} if direction=='projects' else {'role_id':self.data['roles'][0]['role_id']})
        headers={'Content-Type':'application/json'}
        if authenticated:
            headers['Authorization']='Bearer synthetic-test'
        request=HttpRequest(self.base+'/matching/'+direction,data=json.dumps(body).encode(),headers=headers,method='POST')
        try:
            response=urlopen(request,timeout=10)
        except HTTPError as error:
            response=error
        with response:
            return response.status,json.load(response),response.headers

    def test_both_endpoints_use_same_score_and_return_no_store(self):
        a,b=self.request(),self.request('profiles')
        self.assertEqual((a[0],b[0]),(200,200))
        self.assertEqual(a[1]['data']['recommendations'][0]['match'],74)
        self.assertEqual(b[1]['data']['recommendations'][0]['match'],74)
        self.assertEqual(a[2]['Cache-Control'],'no-store')
        self.profile_loader.assert_called_with('synthetic.user',self.data['profile']['profile_id'])

    def test_unauthenticated_cannot_load_data(self):
        for direction in ('projects','profiles'):
            self.assertEqual(self.request(direction,authenticated=False)[0],401)
        self.profile_loader.assert_not_called()
        self.role_loader.assert_not_called()

    def test_permission_denied_precedes_repository_access(self):
        self.allow_profile.return_value=False
        self.allow_role.return_value=False
        self.assertEqual(self.request()[0],403)
        self.assertEqual(self.request('profiles')[0],403)
        self.profile_loader.assert_not_called()
        self.profiles_loader.assert_not_called()

    def test_missing_data_404(self):
        self.profile_loader.return_value=None
        self.role_loader.return_value=None
        self.assertEqual(self.request()[0],404)
        self.assertEqual(self.request('profiles')[0],404)

    def test_client_cannot_submit_scores_or_fake_identity(self):
        for body in ({'profile_id':'profile.demo.1','match':100},{'profile_id':'profile.demo.1','user_id':'owner'}, {'profile_id':1},{'profile_id':' '}):
            self.assertEqual(self.request(body=body)[0],422)
        self.profile_loader.assert_not_called()

    def test_bad_stored_contract_is_500_with_no_pii(self):
        self.profile_loader.return_value['phone']='private-value'
        code,body,_=self.request()
        self.assertEqual(code,500)
        self.assertNotIn('private-value',json.dumps(body))
        self.assertNotIn('data',body)

    def test_identity_mismatch_and_candidate_limit_fail_explicitly(self):
        self.profile_loader.return_value['profile_id']='other'
        self.assertEqual(self.request()[0],500)
        self.profile_loader.return_value=copy.deepcopy(self.data['profile'])
        self.roles_loader.return_value=self.data['roles']*4
        self.assertEqual(self.request()[0],500)

    def test_repository_failure_not_empty_success(self):
        self.roles_loader.side_effect=RuntimeError('private storage failure')
        code,body,_=self.request()
        self.assertEqual(code,503)
        self.assertNotIn('private storage failure',str(body))

    def test_no_ai_and_empty_candidates_work(self):
        self.roles_loader.return_value=[]
        self.assertEqual(self.request()[1]['data']['recommendations'],[])
        self.profiles_loader.return_value=[]
        self.assertEqual(self.request('profiles')[1]['data']['recommendations'],[])

    def test_router_requires_all_dependencies_and_valid_limit(self):
        with self.assertRaises(TypeError):
            create_matching_router()
        with self.assertRaises(ValueError):
            create_matching_router(get_principal=None,authorize_profile=None,authorize_role=None,
                load_profile=None,load_roles=None,load_role=None,load_profiles=None,max_candidates=0)
