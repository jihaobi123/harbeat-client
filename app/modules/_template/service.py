from app.modules._template.schemas import ExampleRequest, ExampleResponse


def run_example(payload: ExampleRequest) -> ExampleResponse:
    return ExampleResponse(name=payload.name)

