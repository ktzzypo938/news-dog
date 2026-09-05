"""Bounded, structured execution evidence; no extra network dependency for crawlers."""
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_url(value):
    try:
        parts = urlsplit(value or '')
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return None
        return urlunsplit((parts.scheme, parts.hostname, parts.path, '', ''))[:600]
    except ValueError:
        return None


class RunTelemetry:
    def __init__(self, source, request, stats):
        self.stats = stats
        self.run_id = str(uuid.uuid4())
        self.source = source
        self.started_at = utc_now()
        self.started_clock = time.monotonic()
        self.last_progress = self.started_clock
        self.sequence = 0
        self.errors = []
        self.error_counts = {}
        self.stage = 'RUNTIME'
        headers = request.headers
        job = headers.get('X-CloudScheduler-JobName', '')
        # Scheduler HTTP targets can send the short job ID instead of a resource path.
        valid_job = job == 'job-scraper-' + source.lower() or re.fullmatch(r'projects/[\w-]+/locations/[\w-]+/jobs/[\w-]+', job)
        self.job_name = job[:300] if valid_job else None
        self.scheduled_at = None
        try:
            value = datetime.fromisoformat(headers.get('X-CloudScheduler-ScheduleTime', '').replace('Z', '+00:00'))
            if value.tzinfo and self.job_name:
                self.scheduled_at = value.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
        trace = headers.get('X-Cloud-Trace-Context', '').split('/')[0]
        self.trace_id = trace if re.fullmatch(r'[0-9a-f]{32}', trace) else None

    def error(self, code, url=None, stage=None, upstream_status=None):
        entry = {'stage': stage or self.stage, 'code': code[:80]}
        if safe_url(url):
            entry['url'] = safe_url(url)
        if isinstance(upstream_status, int):
            entry['upstream_status'] = upstream_status
        key = entry['stage'] + ':' + entry['code']
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
        if len(self.errors) < 5:
            self.errors.append(entry)

    def emit(self, event, outcome='RUNNING', http_status=None):
        self.sequence += 1
        now = utc_now()
        data = {
            'telemetry': 'crawler_run', 'schema_version': 1,
            'event': event, 'event_id': f'{self.run_id}:{self.sequence}',
            'sequence': self.sequence, 'run_id': self.run_id,
            'source_code': self.source, 'started_at': self.started_at,
            'event_at': now, 'duration_ms': round((time.monotonic() - self.started_clock) * 1000),
            'revision': os.getenv('K_REVISION', 'local'), 'service': os.getenv('K_SERVICE', 'local'),
            'trigger_type': 'SCHEDULED' if self.job_name else 'MANUAL',
            'job_name': self.job_name, 'scheduled_at': self.scheduled_at,
            'trace_id': self.trace_id, 'outcome': outcome, 'http_status': http_status,
            'stats': {k: v for k, v in self.stats.items() if isinstance(v, (int, bool))},
            'errors': list(self.errors), 'error_counts': dict(self.error_counts),
            'severity': 'ERROR' if outcome == 'FAILED' else 'WARNING' if outcome == 'WARNING' else 'INFO',
            'message': f'{self.source} {event}: {outcome}',
        }
        data['stats']['accepted'] = data['stats'].pop('ingested', 0)
        if event == 'run_finished':
            data['finished_at'] = now
        print(json.dumps(data, ensure_ascii=False), flush=True)

    def progress(self):
        if time.monotonic() - self.last_progress >= 60:
            self.last_progress = time.monotonic()
            self.emit('run_progress')

    def finish(self, status, exception=False):
        if exception or status >= 500 or (self.stats['failed'] and not self.stats['ingested']):
            outcome = 'FAILED'
        elif self.stats['failed'] or self.stats['deferred']:
            outcome = 'WARNING'
        else:
            outcome = 'SUCCESS'
        self.emit('run_finished', outcome, status)


def context(session):
    return vars(session).get('_crawler_telemetry')


def record_error(session, code, url=None, stage=None, upstream_status=None):
    telemetry = context(session)
    if telemetry:
        telemetry.error(code, url, stage, upstream_status)


def set_stage(session, stage):
    telemetry = context(session)
    if telemetry:
        telemetry.stage = stage
        telemetry.progress()
