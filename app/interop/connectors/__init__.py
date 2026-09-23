"""Reusable connector abstraction: the gateway (app.services.interop_gateway_service) calls every
government system - mock or real - through app.interop.connectors.base.GovernmentConnector, via
the runtime in app.interop.connectors.runtime. It never calls a mock-system query function
directly. See docs/INTEROPERABILITY.md's "Connector abstraction" section."""
