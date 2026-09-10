import json
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / "integrations" / "jd-extraction" / "collector-server.mjs"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                if response.read() == b"ok":
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("collector did not become healthy")


def test_collector_install_page_binds_capture_to_current_project() -> None:
    collector_port = free_port()
    backend_port = free_port()
    received: list[tuple[str, dict]] = []

    class BackendHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            received.append((self.path, json.loads(self.rfile.read(size))))
            body = json.dumps({"id": "jd-1", "status": "COMPLETED"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return

    backend = ThreadingHTTPServer(("127.0.0.1", backend_port), BackendHandler)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    process = subprocess.Popen(
        [
            "node",
            str(COLLECTOR),
            f"--port={collector_port}",
            f"--backend=http://127.0.0.1:{backend_port}",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_health(collector_port)
        project_id = "project-current"
        with urlopen(
            f"http://127.0.0.1:{collector_port}/install?project_id={project_id}",
            timeout=2,
        ) as response:
            install_html = response.read().decode("utf-8")
        assert project_id in install_html
        assert "拖到浏览器书签栏" in install_html
        assert "自动识别站点" in install_html
        for label in ("BOSS 直聘", "Mokahr", "拉勾", "猎聘", "大厂招聘 SPA", "通用网页"):
            assert label in install_html

        payload = {
            "page_title": "前端工程师",
            "url": "https://example.com/job",
            "extracted": {
                "job_title": "前端工程师",
                "description": "岗位职责：负责 React 组件开发、页面性能优化和前端工程化建设。任职要求：熟悉 TypeScript、React 及常用构建工具。",
            },
        }
        request = Request(
            f"http://127.0.0.1:{collector_port}/jd?project_id={project_id}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            result = json.loads(response.read())

        assert result["ok"] is True
        assert result["project_id"] == project_id
        assert result["jd_status"] == "COMPLETED"
        assert received == [(
            f"/api/projects/{project_id}/jds/browser",
            payload,
        )]

        invalid_request = Request(
            f"http://127.0.0.1:{collector_port}/jd?project_id={project_id}",
            data=json.dumps({
                "page_title": "Agent 平台数据智能研发高级工程师-杭州",
                "url": "https://www.zhipin.com/job_detail/example",
                "platform": "boss-zhipin",
                "extracted": {
                    "job_title": "Agent 平台数据智能研发高级工程师-杭州",
                    "description": "下载App, 不错过Boss每一条消息",
                },
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(invalid_request, timeout=3)
            raise AssertionError("noise-only capture should be rejected")
        except HTTPError as exc:
            assert exc.code == 422
            error = json.loads(exc.read())
            assert "没有提取到有效 JD 正文" in error["detail"]
        assert len(received) == 1
    finally:
        process.terminate()
        process.wait(timeout=5)
        backend.shutdown()
        backend.server_close()
