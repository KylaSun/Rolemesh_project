"""Opt-in local analytics store; never imports the backend database configuration.

All identifiers/decisions must come from the trusted authorized backend. These
events are analytics facts, not application/member creation or an auth system.
"""
from contextlib import closing
from datetime import datetime, timezone
from importlib.resources import files
import json
from pathlib import Path
import sqlite3

from .integration import _validate_schema


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Expected timezone-qualified ISO timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Expected timezone-qualified ISO timestamp') from error
    if parsed.utcoffset() is None:
        raise ValueError('Timestamp timezone required')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


class EventStore:
    def __init__(self, database_path):
        self.path = Path(database_path)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def initialize(self):
        """Explicit opt-in schema creation; backend must review before integration."""
        script = files('rolemesh_matching').joinpath('sql', '001_matching_events.sql').read_text(encoding='utf-8')
        with closing(self._connect()) as connection:
            connection.executescript(script)

    def record(self, event):
        _validate_schema(event, 'event')
        event = dict(event)
        event['occurred_at'] = _timestamp(event['occurred_at'])
        kind = event['event_type']
        if kind == 'recommendation_generated' and event['recommendation_id'] != event['event_id']:
            raise ValueError('Recommendation must reference its own event ID')
        encoded = json.dumps(event, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            prior = connection.execute(
                'SELECT event_json FROM matching_events WHERE event_id = ? OR idempotency_key = ?',
                (event['event_id'], event['idempotency_key'])).fetchall()
            if prior:
                if len(prior) != 1:
                    raise ValueError('Conflicting event identifiers')
                saved = json.loads(prior[0]['event_json'])
                # Retrying a stable idempotency key may use a newly allocated event ID.
                before = {k:v for k,v in saved.items() if k != 'event_id'}
                after = {k:v for k,v in event.items() if k != 'event_id'}
                if before != after:
                    raise ValueError('Idempotency key or event ID reused with different data')
                connection.rollback()
                return {'inserted':False, 'event_id':saved['event_id']}
            if kind != 'recommendation_generated':
                row = connection.execute('SELECT event_json FROM matching_events WHERE event_id = ?',
                                         (event['recommendation_id'],)).fetchone()
                if row is None:
                    raise ValueError('Recommendation attribution does not exist')
                parent = json.loads(row['event_json'])
                if parent['event_type'] != 'recommendation_generated':
                    raise ValueError('Attribution must reference a recommendation')
                for key in ('subject_user_id', 'profile_id', 'project_id', 'role_id'):
                    if event[key] != parent[key]:
                        raise ValueError('Event attribution identity mismatch')
                if event['occurred_at'] < parent['occurred_at']:
                    raise ValueError('Event predates its recommendation')
            if kind == 'member_confirmed':
                row = connection.execute(
                    "SELECT event_json FROM matching_events WHERE event_type = 'application_submitted' AND application_id = ?",
                    (event['application_id'],)).fetchone()
                if row is None:
                    raise ValueError('Attributed application does not exist')
                application = json.loads(row['event_json'])
                if application['recommendation_id'] != event['recommendation_id'] or event['occurred_at'] < application['occurred_at']:
                    raise ValueError('Membership does not follow the attributed application')
            connection.execute('''INSERT INTO matching_events
                (event_id,idempotency_key,event_type,occurred_at,actor_user_id,subject_user_id,
                 profile_id,project_id,role_id,recommendation_id,application_id,membership_id,event_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                tuple(event[k] for k in ('event_id','idempotency_key','event_type','occurred_at','actor_user_id',
                      'subject_user_id','profile_id','project_id','role_id','recommendation_id'))
                + (event.get('application_id'), event.get('membership_id'), encoded))
            connection.commit()
            return {'inserted':True, 'event_id':event['event_id']}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def conversion(self, start, end, *, as_of):
        """Per-recommendation cohort, [start,end), outcomes observed through as_of."""
        start, end, as_of = map(_timestamp, (start, end, as_of))
        if not start < end or as_of < end:
            raise ValueError('Expected start < end <= as_of')
        with closing(self._connect()) as connection:
            row = connection.execute('''WITH cohort AS (
                SELECT event_id FROM matching_events
                WHERE event_type = 'recommendation_generated' AND occurred_at >= ? AND occurred_at < ?
            ) SELECT count(DISTINCT c.event_id) AS recommendations,
                count(DISTINCT CASE WHEN e.event_type = 'application_submitted' THEN c.event_id END) AS applications,
                count(DISTINCT CASE WHEN e.event_type = 'member_confirmed' THEN c.event_id END) AS memberships,
                count(DISTINCT CASE WHEN e.event_type = 'feedback_recorded' THEN e.event_id END) AS feedback_events
            FROM cohort c LEFT JOIN matching_events e
                ON e.recommendation_id = c.event_id AND e.occurred_at <= ?''',
                (start,end,as_of)).fetchone()
        result = dict(row)
        r,a,m = (result[k] for k in ('recommendations','applications','memberships'))
        result.update(recommendation_to_application=a/r if r else None,
                      application_to_membership=m/a if a else None,
                      recommendation_to_membership=m/r if r else None)
        return result
