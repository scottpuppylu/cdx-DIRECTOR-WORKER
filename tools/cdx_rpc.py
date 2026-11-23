"""Codex App Server JSON-RPC over a local stdio process."""

import json
import queue
import subprocess
import threading
import time


class RPCTimeout(RuntimeError):
    pass


class RPCError(RuntimeError):
    def __init__(self, method, error):
        self.code = error.get("code")
        # Keep provider details out of user-facing errors. Only recognize the exact missing-rollout case.
        self.missing_rollout = (method in ("thread/read", "thread/resume") and self.code == -32600 and
                                str(error.get("message", "")).lower().startswith("no rollout found for thread id"))
        super().__init__(f"App Server rejected {method} (code {self.code})")


class AppServer:
    def __init__(self, executable, cwd, on_event=None, *, env=None, overrides=()):
        self.executable = executable
        self.cwd = cwd
        self.on_event = on_event
        self.env = env
        self.overrides = overrides
        self.inbox = queue.Queue()
        self.id = 0

    def __enter__(self):
        command = [self.executable]
        for setting in self.overrides:
            command.extend(("-c", setting))
        self.process = subprocess.Popen([*command, "app-server", "--listen", "stdio://"], cwd=self.cwd,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8", env=self.env)
        threading.Thread(target=self.read, daemon=True).start()
        try:
            self.call("initialize", {"clientInfo": {"name": "cdx_director_work", "version": "1"}})
            self.send({"method": "initialized"})
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdout.close()

    def read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("App Server message is not a JSON object")
                self.inbox.put(message)
        except (UnicodeError, ValueError, OSError) as error:
            self.inbox.put(error)
        finally:
            self.inbox.put(None)

    def send(self, data):
        self.process.stdin.write(json.dumps(data, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def refuse_request(self, message):
        method = message["method"]
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            reply = {"result": {"decision": "decline"}}
        elif method == "item/permissions/requestApproval":
            reply = {"result": {"permissions": {}, "scope": "turn"}}
        else:
            reply = {"error": {"code": -32601, "message": "cdx does not answer this host request automatically"}}
        self.send(dict(reply, id=message["id"]))

    def receive(self, match, timeout, purpose):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self.inbox.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                break
            if message is None or isinstance(message, Exception):
                raise RuntimeError(f"App Server stream ended while waiting for {purpose}")
            if "method" in message:
                if self.on_event:
                    self.on_event(message)
                if "id" in message:
                    self.refuse_request(message)
            if match(message):
                return message
        raise RPCTimeout(f"Timed out waiting for {purpose}")

    def call(self, method, params, timeout=35):
        self.id += 1
        rid = self.id
        self.send({"id": rid, "method": method, "params": params})
        reply = self.receive(lambda item: item.get("id") == rid and "method" not in item, timeout, method)
        if "error" in reply:
            raise RPCError(method, reply["error"])
        return reply["result"]
