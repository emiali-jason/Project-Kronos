from pathlib import Path


def pytest_addoption(parser):
    parser.addoption("--theta-qualification-output", default=None,
                     help="Explicit non-production directory for synthetic PDF/Browser QA artifacts")
    parser.addoption("--theta-v3-contract-output", default=None,
                     help="Explicit isolated directory for TE-04A synthetic contract artifacts")
    parser.addoption("--theta-combined-intake-output", default=None,
                     help="Explicit isolated directory for TE-04B synthetic intake rehearsal artifacts")
    parser.addoption("--theta-v3-producer-output", default=None,
                     help="Explicit isolated directory for TE-04C synthetic producer rehearsal artifacts")


def qualification_output(request):
    value = request.config.getoption("--theta-qualification-output")
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute() or path.name != "theta-te01-qualification":
        raise ValueError("THETA_QUALIFICATION_OUTPUT_INVALID")
    path = path.resolve()  # Shared kernel/test guard forbids production paths.
    path.mkdir(parents=True, exist_ok=True)
    return path
