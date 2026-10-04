"""Create a fixed React scaffold, repair build/runtime errors, and serve a local preview."""

import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai.llm import LLMError
from core.models import Result
from tools.coding import WORKSPACE

DEPENDENCIES = {"react": "19.3.0", "react-dom": "19.3.0", "vite": "8.3.0"}


def validate_source(code, css):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    # Vite may resolve file imports while building; only React module imports are allowed.
    imports = re.findall(r"""\b(?:from|import)\s*["']([^"']+)["']""", code)
    if (
        any(name != "react" for name in imports)
        or re.search(r"\bimport\s*(?:\(|\.)|\bnew\s+URL\s*\(|\brequire\s*\(", code)
        or re.search(r"@import|url\s*\(", css, re.IGNORECASE)
    ):
        raise ValueError(
            "React source may only import React and use local CSS without external assets."
        )


class PreviewHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; "
            "form-action 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'",
        )
        super().end_headers()

    def log_message(self, *args):
        pass


class ReactWorkflow:
    def __init__(self, client, coding):
        self.client = client
        self.coding = coding
        self.server = None

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def create_react_app(self, request):
        npm = shutil.which("npm")
        node = shutil.which("node")
        if not npm or not node:
            return Result(False, "RUNTIME_UNAVAILABLE", "Install Node.js 22.12+ and npm first.")
        WORKSPACE.mkdir(parents=True, exist_ok=True, mode=0o700)
        project = Path(tempfile.mkdtemp(prefix="React_", dir=WORKSPACE))
        # Only this fixed scaffold controls dependencies and build commands.
        (project / "package.json").write_text(
            json.dumps(
                {
                    "name": "lucifer-react-app",
                    "version": "1.0.0",
                    "private": True,
                    "type": "module",
                    "scripts": {"dev": "vite --host 127.0.0.1", "build": "vite build"},
                    "dependencies": DEPENDENCIES,
                },
                indent=2,
            )
        )
        (project / "index.html").write_text(
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>Lucifer React App</title></head>'
            '<body><div id="root"></div><script type="module" src="/main.jsx"></script></body></html>'
        )
        (project / "main.jsx").write_text(
            'import React from "react"; import {createRoot} from "react-dom/client"; '
            'import App from "./App.jsx"; import "./App.css"; '
            'createRoot(document.getElementById("root")).render(<App/>);'
        )
        (project / "vite.config.js").write_text(
            'export default {plugins:[{name:"lucifer-import-policy", enforce:"pre", '
            'resolveId(source,importer){if(importer && importer.split("?")[0].endsWith("/App.jsx") '
            '&& !["react","react/jsx-runtime","react/jsx-dev-runtime"].includes(source)) '
            'throw new Error("Only React imports are allowed in App.jsx: " + source);}}]};'
        )
        env = {
            name: os.environ[name]
            for name in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")
            if name in os.environ
        }
        env["CI"] = "1"
        try:
            installed = subprocess.run(
                [npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
                check=False,
            )
            if installed.returncode:
                return Result(
                    False,
                    "DEPENDENCY_FAILED",
                    "React dependencies could not be installed.",
                    {"project": str(project)},
                )
            diagnostics = ""
            previous = ""
            for attempt in range(3):
                plan = self.client.complete_json(
                    "Create a complete polished React app implementing the user request. "
                    'Return JSON {"code":"App.jsx source","css":"App.css","summary":"one sentence"}. '
                    "Export default function App. Import React and hooks from react. Only react "
                    "imports are installed; use native HTML controls and CSS, no other packages. "
                    "No network requests, external resources, eval, dynamic imports, storage of "
                    "secrets or process access. Forms must prevent default submission and show "
                    "local validation/success feedback. This is a frontend-only local app. "
                    f"Request: {json.dumps(request)}\nPrevious source: {previous}\n"
                    f"Fix these build/runtime errors if present: {diagnostics}"
                )
                if (
                    set(plan) != {"code", "css", "summary"}
                    or any(not isinstance(v, str) or len(v) > 60000 for v in plan.values())
                    or not plan["code"].strip()
                ):
                    raise ValueError("AI returned an invalid React source plan.")
                previous = plan["code"]
                validate_source(plan["code"], plan["css"])
                (project / "App.jsx").write_text(plan["code"], encoding="utf-8")
                (project / "App.css").write_text(plan["css"], encoding="utf-8")
                built = subprocess.run(
                    [node, str(project / "node_modules/vite/bin/vite.js"), "build"],
                    cwd=project,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                diagnostics = (built.stdout + built.stderr)[-6000:]
                if built.returncode:
                    continue
                self.close()
                self.server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    functools.partial(PreviewHandler, directory=str(project / "dist")),
                )
                threading.Thread(target=self.server.serve_forever, daemon=True).start()
                url = f"http://127.0.0.1:{self.server.server_port}"
                diagnostics = self._check_preview(url)
                if diagnostics:
                    self.close()
                    continue
                self.coding._open_project(project)
                from tools.browser import open_url

                opened = open_url(url)
                return Result(
                    opened.ok,
                    "REACT_READY" if opened.ok else opened.code,
                    f"Created and built your React app, checked browser startup, and opened "
                    f"VS Code. Preview: {url}" + ("" if opened.ok else "\n" + opened.message),
                    {
                        "project": str(project),
                        "url": url,
                        "attempts": attempt + 1,
                        "summary": plan["summary"],
                    },
                )
            return Result(
                False,
                "REACT_BUILD_FAILED",
                "React still has errors after three attempts. "
                f"Source saved in {project}.\n{diagnostics}",
                {"project": str(project)},
            )
        except LLMError as error:
            return Result(False, "MODEL_UNAVAILABLE", str(error), {"project": str(project)})
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.close()
            return Result(
                False,
                "REACT_FAILED",
                f"React setup or verification failed. Source saved in {project}.",
            )

    def _check_preview(self, url):
        from playwright.sync_api import Error, sync_playwright

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(service_workers="block")
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(url + "/")
                        else route.abort()
                    ),
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(500)
                if not page.locator("#root").inner_text().strip():
                    errors.append("The application rendered no visible text.")
                browser.close()
                return "\n".join(errors)[:6000]
        except Error:
            raise ValueError("Could not verify the app in Chrome.") from None
