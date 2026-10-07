"""OpenTelemetry setup. Tracing is a no-op unless OTEL_ENABLED=true, so spans can be used everywhere."""
from opentelemetry import trace

from app.core.config import get_settings

tracer = trace.get_tracer("sfai")


def setup_telemetry(app=None) -> None:
    s = get_settings()
    if not s.otel_enabled:
        return
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    provider = TracerProvider(resource=Resource.create({"service.name": s.otel_service_name}))
    if s.otel_exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
        exporter = OTLPSpanExporter()
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
