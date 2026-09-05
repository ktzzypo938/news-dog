import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from werkzeug.datastructures import Headers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
import main
from telemetry import RunTelemetry


class TelemetryTests(unittest.TestCase):
    def invoke(self, source, urls):
        request = SimpleNamespace(args={'source': 'CTS'}, headers={})
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(main.importlib, 'import_module', return_value=source), \
                patch.object(base, 'get_new_urls', return_value=urls), patch.object(base, 'ingest_article', return_value=True), \
                patch.object(base, 'SCRAPER_ONLY_TODAY', False), patch.object(base, 'SKIP_URL_CACHE', {}):
            result = main.run_scraper(request)
        events = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
        return result, events

    def test_partial_work_survives_unexpected_exception(self):
        source = SimpleNamespace(get_list_urls=Mock(return_value=['a', 'b']), scrape_article=Mock(side_effect=[
            {'title': 'News', 'cleanText': 'Content.', 'publishedAt': '2026-09-05 12:00:00'}, RuntimeError('private detail')]))
        response, events = self.invoke(source, ['a', 'b'])
        self.assertEqual(response[1], 500)
        self.assertEqual([e['event'] for e in events], ['run_started', 'run_finished'])
        self.assertEqual(events[-1]['stats']['accepted'], 1)
        self.assertEqual(events[-1]['outcome'], 'FAILED')
        self.assertNotIn('private detail', json.dumps(events))

    def test_empty_valid_list_finishes_successfully(self):
        def listing(session):
            session._scraper_list_valid = True
            return []
        response, events = self.invoke(SimpleNamespace(get_list_urls=listing), [])
        self.assertEqual(response[1], 200)
        self.assertEqual(events[-1]['outcome'], 'SUCCESS')

    def test_blocked_source_has_finished_failure(self):
        source = SimpleNamespace(get_list_urls=Mock(side_effect=base.SourceFetchError('blocked')))
        response, events = self.invoke(source, [])
        self.assertEqual(response[1], 503)
        self.assertEqual(events[-1]['errors'][0]['stage'], 'LIST_FETCH')

    def test_scheduler_retries_have_distinct_runs_and_same_slot(self):
        request = SimpleNamespace(headers={'X-CloudScheduler-JobName': 'projects/test/locations/asia-east1/jobs/job-scraper-cts',
                                           'X-CloudScheduler-ScheduleTime': '2026-09-05T05:03:00Z'})
        first, retry = RunTelemetry('CTS', request, base.empty_run_stats()), RunTelemetry('CTS', request, base.empty_run_stats())
        self.assertNotEqual(first.run_id, retry.run_id)
        self.assertEqual(first.scheduled_at, retry.scheduled_at)

    def test_actual_scheduler_short_job_and_offset_timestamp_are_preserved(self):
        request = SimpleNamespace(headers=Headers({
            'X-Cloudscheduler-Jobname': 'job-scraper-cts',
            'X-Cloudscheduler-Scheduletime': '2026-09-04T22:42:01.90066-07:00'}))
        run = RunTelemetry('CTS', request, base.empty_run_stats())
        self.assertEqual(run.job_name, 'job-scraper-cts')
        self.assertEqual(run.scheduled_at, '2026-09-05T05:42:01.900660+00:00')
        with contextlib.redirect_stdout(io.StringIO()) as output: run.emit('run_started')
        self.assertEqual(json.loads(output.getvalue())['trigger_type'], 'SCHEDULED')

    def test_short_job_for_a_different_source_is_not_trusted(self):
        request = SimpleNamespace(headers={'X-CloudScheduler-JobName': 'job-scraper-tvbs',
                                           'X-CloudScheduler-ScheduleTime': '2026-09-05T05:03:00Z'})
        run = RunTelemetry('CTS', request, base.empty_run_stats())
        self.assertIsNone(run.job_name)
        self.assertIsNone(run.scheduled_at)

    def test_error_samples_are_bounded_and_urls_have_no_credentials(self):
        run = RunTelemetry('CTS', SimpleNamespace(headers={}), base.empty_run_stats())
        for _ in range(20): run.error('HTTP_403', 'https://name:secret@example.com/article?token=private#fragment')
        self.assertEqual(len(run.errors), 5)
        self.assertEqual(run.errors[0]['url'], 'https://example.com/article')
        self.assertEqual(run.error_counts['RUNTIME:HTTP_403'], 20)

    def test_rate_limited_partial_batch_is_warning_even_with_http_200(self):
        stats = base.empty_run_stats(); stats['deferred'] = 10
        run = RunTelemetry('CTI', SimpleNamespace(headers={}), stats)
        with contextlib.redirect_stdout(io.StringIO()) as out: run.finish(200)
        self.assertEqual(json.loads(out.getvalue())['outcome'], 'WARNING')

    def test_single_real_failure_is_not_healthy(self):
        stats = base.empty_run_stats(); stats['failed'] = 1
        run = RunTelemetry('CTI', SimpleNamespace(headers={}), stats)
        with contextlib.redirect_stdout(io.StringIO()) as out: run.finish(200)
        self.assertEqual(json.loads(out.getvalue())['outcome'], 'FAILED')

    def test_progress_emits_at_interval(self):
        run = RunTelemetry('CTI', SimpleNamespace(headers={}), base.empty_run_stats())
        run.last_progress -= 61
        with contextlib.redirect_stdout(io.StringIO()) as out:
            run.progress(); run.progress()
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(out.getvalue())['event'], 'run_progress')
