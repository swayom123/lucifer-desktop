"""Guarded local coding workflow: generate, validate, compile, run and open a project."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from ai.llm import LLMClient, LLMError
from automation.application_registry import ApplicationRegistry
from core.models import Result

SUPPORTED = {"c": ".c", "c++": ".cpp", "cpp": ".cpp", "python": ".py", "javascript": ".js"}
WORKSPACE = Path.home() / "LuciferProjects"
FORBIDDEN = re.compile(
    r"(?:rm\s+-rf|sudo|system\s*\(|popen\s*\(|subprocess|os\.system|socket|fork\s*\(|exec\s*\(|eval\s*\(|__import__|shutil\.rmtree|curl\s|wget\s|(?:^|[\s<])(?:unistd|sys/|arpa|netinet)|\b(?:fopen|freopen|remove|unlink|rename|dlopen|execve)\s*\(|(?:os\.)?(?:open|remove|rename|unlink|listdir|walk)\s*\()",
    re.IGNORECASE,
)


class CodingWorkflow:
    def __init__(self, apps: ApplicationRegistry, client: LLMClient | None = None):
        self.apps = apps
        self.client = client or LLMClient()

    def generate_program(self, request: str, language: str) -> Result:
        language = language.casefold().strip()
        if language not in SUPPORTED:
            raise ValueError("Supported coding languages are C, C++, Python and JavaScript.")
        if not request.strip() or len(request) > 1200:
            raise ValueError("Describe a program in 1–1200 characters.")
        WORKSPACE.mkdir(parents=True, exist_ok=True, mode=0o700)
        project = None
        repair_context = ""
        for attempt in range(2):
            try:
                plan = self.client.generate_program(request, language, repair_context)
                project, _source, summary = self._validate_plan(plan, language)
                project.mkdir(parents=True, exist_ok=True, mode=0o700)
                project.chmod(0o700)
                source_path = project / plan["file_name"]
                source_path.write_text(plan["code"], encoding="utf-8")
                source_path.chmod(0o600)
                result = self._compile_and_check(project, source_path, language)
                if result.ok:
                    self._open_project(project)
                    data = {
                        **result.data,
                        "project": str(project),
                        "source": str(source_path),
                        "summary": summary,
                        "attempts": attempt + 1,
                    }
                    return Result(
                        True,
                        result.code,
                        f"Created {source_path.name}, compiled it successfully, and opened {project.name} in VS Code.",
                        data,
                    )
                repair_context = result.message
            except LLMError as error:
                return Result(False, "MODEL_UNAVAILABLE", str(error))
            except (OSError, ValueError) as error:
                return Result(False, "CODE_WORKFLOW_FAILED", str(error))
        return Result(
            False,
            "COMPILE_FAILED",
            f"The generated program did not compile after two attempts.\n{repair_context}",
            {"project": str(project) if project else ""},
        )

    def _validate_plan(self, plan: dict, language: str) -> tuple[Path, Path, str]:
        required = {"project_name", "file_name", "code", "summary"}
        if set(plan) != required or not all(isinstance(plan[key], str) for key in required):
            raise ValueError("The coding model returned an incomplete program plan.")
        if len(plan["code"]) > 100_000 or len(plan["summary"]) > 1_000:
            raise ValueError("The coding model returned an oversized program plan.")
        plan["code"] = _normalize_source(plan["code"])
        if FORBIDDEN.search(plan["code"]):
            raise ValueError(
                "The generated source requested a blocked system or process operation."
            )
        filename = plan["file_name"]
        if (
            Path(filename).name != filename
            or not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9]+", filename)
            or not filename.endswith(SUPPORTED[language])
            or len(filename) > 100
        ):
            raise ValueError("The coding model returned an unsafe source filename.")
        project_name = re.sub(r"[^A-Za-z0-9]+", "_", plan["project_name"]).strip("_")[:80]
        if not project_name:
            raise ValueError("The coding model returned an empty project name.")
        project = (WORKSPACE / project_name).resolve()
        if not project.is_relative_to(WORKSPACE.resolve()):
            raise ValueError("Project path escaped the Lucifer workspace.")
        return project, project / filename, plan["summary"]

    def _compile_and_check(self, project: Path, source: Path, language: str) -> Result:
        started = time.monotonic()
        if language == "c":
            compiler = shutil.which("gcc") or shutil.which("clang")
            if not compiler:
                return Result(
                    False, "COMPILER_UNAVAILABLE", "No C compiler (gcc or clang) is installed."
                )
            binary = project / "program"
            command = [
                compiler,
                "-std=c17",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-O2",
                str(source),
                "-o",
                str(binary),
            ]
            run_command = [str(binary)]
        elif language in {"c++", "cpp"}:
            compiler = shutil.which("g++") or shutil.which("clang++")
            if not compiler:
                return Result(False, "COMPILER_UNAVAILABLE", "No C++ compiler is installed.")
            binary = project / "program"
            command = [
                compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-O2",
                str(source),
                "-o",
                str(binary),
            ]
            run_command = [str(binary)]
        elif language == "python":
            command = [
                shutil.which("python3") or os.sys.executable,
                "-m",
                "py_compile",
                str(source),
            ]
            run_command = [shutil.which("python3") or os.sys.executable, str(source)]
        else:
            node = shutil.which("node")
            if not node:
                return Result(False, "RUNTIME_UNAVAILABLE", "Node.js is not installed.")
            command = [node, "--check", str(source)]
            run_command = [node, str(source)]
        try:
            compiled = subprocess.run(
                command, cwd=project, capture_output=True, text=True, timeout=20, check=False
            )
            diagnostics = (compiled.stdout + compiled.stderr).strip()
            if compiled.returncode:
                return Result(
                    False, "COMPILE_FAILED", diagnostics[-6000:] or "Compiler returned an error."
                )
            executed = subprocess.run(
                run_command,
                cwd=project,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env={"PATH": os.getenv("PATH", "")},
            )
            output = (executed.stdout + executed.stderr).strip()
            if executed.returncode:
                return Result(
                    False, "PROGRAM_FAILED", output[-6000:] or "Program exited with an error."
                )
            return Result(
                True,
                "PROGRAM_VERIFIED",
                f"Compiled and ran successfully in {time.monotonic() - started:.1f}s.",
                {"output": output[-6000:], "diagnostics": diagnostics},
            )
        except subprocess.TimeoutExpired:
            return Result(
                False, "PROGRAM_TIMEOUT", "Compilation or execution exceeded its time limit."
            )

    def _open_project(self, project: Path) -> None:
        command = self.apps.command(self.apps.resolve("vscode"))
        if not command:
            raise OSError("VS Code does not appear to be installed.")
        subprocess.Popen(
            [*command, str(project)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=self.apps.system != "Windows",
        )


def _normalize_source(code: str) -> str:
    """Repair providers that double-escape source line breaks inside JSON strings."""
    if code.count("\n") >= 3 or code.count(r"\n") < 4:
        return code
    return re.sub(
        r"\\n(?=\s*(?:#|/\*|\*/|(?:static\s+)?(?:int|void|char|size_t|return|for|while|if|else)|\}))",
        "\n",
        code,
    )
