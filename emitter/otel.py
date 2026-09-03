"""OTel metrics + logs pipeline for replaying one shooting day.

Metrics are exposed as observable gauges that read a mutable (day, now)
snapshot at collection time, so emitter/schedule.py stays the single
source of truth for every reading -- this module never recomputes the
maths, it only wires schedule.py's functions to the SDK.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from emitter import schedule
from emitter.models import ShootingDay

_EXPORT_INTERVAL_MILLIS = 60_000
"""Background export cadence. Instruments.flush() drives the actual
per-step export during replay, so this is just a fallback."""


class Instruments:
    """Bundles the OTel metric + log pipeline for one shooting-day replay."""

    def __init__(self, day: ShootingDay, dry_run: bool = False) -> None:
        self._day = day
        self._now = day.general_call

        resource = Resource.create(
            {
                "service.name": "martini",
                "production.title": day.production_title,
                "day.number": day.day_number,
            }
        )

        metric_exporter = ConsoleMetricExporter() if dry_run else OTLPMetricExporter()
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    metric_exporter, export_interval_millis=_EXPORT_INTERVAL_MILLIS
                )
            ],
        )
        meter = self._meter_provider.get_meter("martini.emitter")

        log_exporter = ConsoleLogRecordExporter() if dry_run else OTLPLogExporter()
        self._logger_provider = LoggerProvider(resource=resource)
        self._logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
        self._logger = self._logger_provider.get_logger("martini.emitter")

        self._register_gauges(meter)
        self.takes_total = meter.create_counter(
            "martini_takes_total", description="Takes printed, by scene"
        )
        self.setups_wrapped = meter.create_counter(
            "martini_setups_wrapped", description="Setups wrapped, by scene"
        )

    def _register_gauges(self, meter) -> None:
        def gauge(name: str, fn: Callable[[ShootingDay, datetime], float]) -> None:
            def callback(options: CallbackOptions):
                yield Observation(fn(self._day, self._now))

            meter.create_observable_gauge(name, callbacks=[callback])

        gauge("martini_error_budget_consumed", schedule.error_budget_consumed)
        gauge("martini_burn_rate", schedule.burn_rate)
        gauge("martini_pages_completed_eighths", lambda day, now: day.completed_page_eighths.eighths)
        gauge("martini_pages_remaining_eighths", lambda day, now: day.remaining_page_eighths.eighths)
        gauge("martini_setups_completed", lambda day, now: day.completed_setups)
        gauge("martini_setups_total", lambda day, now: day.total_setups)
        gauge(
            "martini_projected_wrap_offset_minutes",
            lambda day, now: (schedule.projected_wrap(day, now) - day.scheduled_wrap).total_seconds() / 60,
        )
        gauge("martini_minutes_to_golden_hour", schedule.minutes_to_golden_hour)

    @property
    def now(self) -> datetime:
        return self._now

    def advance(self, now: datetime) -> None:
        self._now = now

    def record_takes(self, scene: str, count: int) -> None:
        self.takes_total.add(count, {"scene": scene})

    def record_setup_wrapped(self, scene: str) -> None:
        self.setups_wrapped.add(1, {"scene": scene})

    def log_event(self, body: str, *, scene: str | None = None, setup: str | None = None) -> None:
        # The record's wire timestamp is left to the SDK (real emission
        # time) so log backends with an ingestion-age window accept it
        # even when the shooting day's own calendar date has drifted
        # from today. The story clock still belongs in the log, just as
        # an attribute rather than the wire timestamp.
        attributes: dict[str, str] = {"day_time": self._now.strftime("%H:%M")}
        if scene is not None:
            attributes["scene"] = scene
        if setup is not None:
            attributes["setup"] = setup
        self._logger.emit(
            severity_number=SeverityNumber.INFO,
            body=body,
            attributes=attributes,
        )

    def flush(self) -> None:
        self._meter_provider.force_flush()
        self._logger_provider.force_flush()

    def shutdown(self) -> None:
        self._meter_provider.shutdown()
        self._logger_provider.shutdown()
