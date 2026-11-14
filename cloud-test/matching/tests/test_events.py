import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from rolemesh_matching.events import EventStore
from rolemesh_matching.integration import ContractError


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EventStore(Path(self.temp.name)/'isolated.sqlite')
        self.store.initialize()

    def event(self,kind='recommendation_generated',**values):
        event = dict(event_version='1.0.0',event_id='rec.1',idempotency_key='request.1/profile.1/role.1',
            event_type=kind,occurred_at='2026-11-08T10:00:00Z',actor_user_id='user.1',subject_user_id='user.1',
            profile_id='profile.1',project_id='project.1',role_id='role.1',recommendation_id='rec.1')
        if kind == 'recommendation_generated':
            event.update(algorithm_version='0.1.1-draft',profile_version=1,role_version=1)
        if kind in ('application_submitted','member_confirmed'):
            event.update(application_id='application.1',occurred_at='2026-11-08T10:01:00Z',event_id='app.event',idempotency_key='application.1/submitted')
        if kind == 'member_confirmed':
            event.update(membership_id='membership.1',occurred_at='2026-11-08T10:02:00Z',event_id='member.event',idempotency_key='membership.1/confirmed')
        if kind == 'feedback_recorded':
            event.update(event_id='feedback.1',idempotency_key='feedback.1',feedback='not_relevant',reason_code='skills')
        event.update(values)
        return event

    def conversion(self,**values):
        params = dict(start='2026-11-08T00:00:00Z',end='2026-11-09T00:00:00Z',as_of='2026-11-10T00:00:00Z')
        params.update(values)
        return self.store.conversion(**params)

    def test_cohort_conversion_and_feedback(self):
        for kind in ('recommendation_generated','application_submitted','member_confirmed','feedback_recorded'):
            event = self.event(kind)
            self.assertTrue(self.store.record(event)['inserted'])
            self.assertFalse(self.store.record(event)['inserted'])
        out = self.conversion()
        self.assertEqual((out['recommendations'],out['applications'],out['memberships'],out['feedback_events']),(1,1,1,1))
        self.assertEqual(out['recommendation_to_membership'],1)

    def test_concurrent_retries_count_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _:self.store.record(self.event()),range(12)))
        self.assertEqual(sum(x['inserted'] for x in results),1)
        self.assertEqual(self.conversion()['recommendations'],1)

    def test_retry_idempotency_and_conflict_rollbacks(self):
        self.store.record(self.event())
        out = self.store.record(self.event(occurred_at='2026-11-08T18:00:00+08:00'))
        self.assertFalse(out['inserted'])
        with self.assertRaises(ValueError):
            self.store.record(self.event(role_id='other'))
        self.assertEqual(self.conversion()['recommendations'],1)

    def test_attribution_cannot_cross_users_or_roles(self):
        self.store.record(self.event())
        for key in ('subject_user_id','profile_id','project_id','role_id'):
            with self.assertRaises(ValueError):
                self.store.record(self.event('application_submitted',**{key:'unrelated'}))
        self.assertEqual(self.conversion()['applications'],0)

    def test_recommendation_and_application_are_required_parents(self):
        with self.assertRaises(ValueError):
            self.store.record(self.event('application_submitted'))
        self.store.record(self.event())
        with self.assertRaises(ValueError):
            self.store.record(self.event('member_confirmed'))

    def test_no_pii_or_unknown_fields_and_no_missing_ids(self):
        for values in ({'email':'private@example.invalid'},{'subject_user_id':''},{'occurred_at':'2026-11-08T10:00:00'}, {'event_version':'next'}):
            with self.assertRaises(ContractError):
                self.store.record(self.event(**values))
        self.assertEqual(self.conversion()['recommendations'],0)

    def test_empty_denominator_is_null(self):
        out = self.conversion()
        self.assertIsNone(out['recommendation_to_application'])
        self.assertIsNone(out['application_to_membership'])

    def test_multiple_applications_for_one_exposure_do_not_inflate_rates(self):
        self.store.record(self.event())
        self.store.record(self.event('application_submitted'))
        self.store.record(self.event('application_submitted',application_id='application.2',event_id='app.2',idempotency_key='app.2'))
        self.assertEqual(self.conversion()['applications'],1)

    def test_business_application_cannot_be_recounted_under_new_event_id(self):
        self.store.record(self.event())
        self.store.record(self.event('application_submitted'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record(self.event('application_submitted',event_id='app.other',idempotency_key='other'))
        self.assertEqual(self.conversion()['applications'],1)

    def test_time_order_and_observation_cutoff(self):
        self.store.record(self.event())
        with self.assertRaises(ValueError):
            self.store.record(self.event('application_submitted',occurred_at='2026-11-08T09:00:00Z'))
        self.store.record(self.event('application_submitted',occurred_at='2026-11-10T10:00:00Z'))
        self.assertEqual(self.conversion()['applications'],0)
        self.assertEqual(self.conversion(as_of='2026-11-11T00:00:00Z')['applications'],1)

    def test_cohort_end_exclusive_and_later_conversion_included(self):
        self.store.record(self.event())
        self.store.record(self.event(event_id='rec.2',recommendation_id='rec.2',idempotency_key='rec.2',occurred_at='2026-11-09T00:00:00Z'))
        self.store.record(self.event('application_submitted',occurred_at='2026-11-09T12:00:00Z'))
        out = self.conversion()
        self.assertEqual(out['recommendations'],1)
        self.assertEqual(out['applications'],1)

    def test_wrong_parent_type_and_mismatched_application_rejected(self):
        self.store.record(self.event())
        self.store.record(self.event('application_submitted'))
        with self.assertRaises(ValueError):
            self.store.record(self.event('feedback_recorded',recommendation_id='app.event'))
        self.store.record(self.event(event_id='rec.2',recommendation_id='rec.2',idempotency_key='rec.2'))
        with self.assertRaises(ValueError):
            self.store.record(self.event('member_confirmed',recommendation_id='rec.2'))

    def test_schema_initialization_repeatable_and_range_validation(self):
        self.store.initialize()
        with self.assertRaises(ValueError):
            self.conversion(end='2026-11-08T00:00:00Z')
        with self.assertRaises(ValueError):
            self.conversion(as_of='2026-11-08T00:00:00Z')
