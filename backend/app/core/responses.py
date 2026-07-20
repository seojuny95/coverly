"""Shared response classes for HTTP routes."""

from fastapi.responses import JSONResponse


class EventStreamOpenAPIResponse(JSONResponse):
    """Declare the event media type while runtime delivery remains streaming.

    FastAPI reads ``response_class.media_type`` to key the documented 200
    response, so an SSE route needs this to publish its event schema. Clients
    generate their stream validators from that schema.
    """

    media_type = "text/event-stream"
