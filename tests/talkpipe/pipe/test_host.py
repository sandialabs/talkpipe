import pytest

from talkpipe.pipe.host import HostContext, HostRequest, drive_host


def test_drive_host_resumes_program_with_results_in_order():
    calls = []

    class Handler:
        def perform(self, request: HostRequest, context: HostContext):
            calls.append((request, context.request_index))
            if request.operation == "read_digest":
                return "sha256:abc"
            return {"ok": True, "digest": request.arguments["digest"]}

    def program():
        digest = yield HostRequest("workspace", "read_digest", {"path": "src"})
        return (yield HostRequest("assurance", "verify", {"digest": digest}))

    assert drive_host(program(), Handler()) == {"ok": True, "digest": "sha256:abc"}
    assert [index for _, index in calls] == [0, 1]


def test_drive_host_throws_handler_errors_back_into_program():
    class Denied(Exception):
        pass

    class Handler:
        def perform(self, request: HostRequest, context: HostContext):
            raise Denied(request.operation)

    def program():
        try:
            yield HostRequest("machine", "exec", {"argv": ["false"]})
        except Denied:
            return "blocked"
        return "unexpected"

    assert drive_host(program(), Handler()) == "blocked"


def test_drive_host_rejects_non_request_yields():
    class Handler:
        def perform(self, request: HostRequest, context: HostContext):
            return None

    def program():
        yield "implicit side effect"

    with pytest.raises(TypeError, match="HostRequest"):
        drive_host(program(), Handler())


def test_host_request_copies_and_freezes_arguments():
    arguments = {"path": "src"}
    request = HostRequest("workspace", "read", arguments)
    arguments["path"] = "elsewhere"

    assert request.arguments["path"] == "src"
    with pytest.raises(TypeError):
        request.arguments["path"] = "mutated"
