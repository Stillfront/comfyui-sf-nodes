# ABOUTME: Shared helpers for nodes that call WaveSpeed's v3 prediction API directly
# ABOUTME: Result polling with interrupt support, and readable errors for a rejected API key

import time

RESULT_PATH = "/api/v3/predictions/{id}/result"
TERMINAL_FAILURES = {"failed", "cancelled", "timeout", "deleted"}


def check_interrupted():
    """Raise if the user pressed Cancel in ComfyUI; a no-op outside ComfyUI."""
    try:
        import comfy.model_management as mm
    except ImportError:
        return
    mm.throw_exception_if_processing_interrupted()


def wait_for_result(api, task_id, timeout_seconds, label, interval=2):
    """Poll a prediction until it completes. Returns the result dict."""
    started = time.time()
    while True:
        check_interrupted()
        result = api.get(RESULT_PATH.format(id=task_id))
        status = result.get("status")
        if status == "completed":
            return result
        if status in TERMINAL_FAILURES:
            raise RuntimeError(f"{label} task {status}: {result.get('error') or result}")
        if time.time() - started > timeout_seconds:
            raise RuntimeError(f"{label} task {task_id} still '{status}' after {timeout_seconds}s.")
        time.sleep(interval)


def call(client, action):
    """Run an API call, turning a 401 into an error that says which key was used."""
    try:
        return action()
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            source = client.get("source", "the SF WaveSpeed Client node")
            raise RuntimeError(
                f"WaveSpeed rejected the API key, which came from {source}. "
                f"Check it on wavespeed.ai under API Keys, or clear the api_key field "
                f"on SF WaveSpeed Client to fall back to a key saved elsewhere."
            ) from e
        raise
