import pytest

from ai.llm import LLMError, _parse_json
from automation.application_registry import ApplicationRegistry
from core.intent_parser import parse
from tools import coding
from tools.coding import CodingWorkflow


def test_program_command_parses_language_and_request():
    action = parse("Lucifer write a program for merge sort in C")
    assert action.tool == "generate_program"
    assert action.arguments == {"request": "merge sort", "language": "c"}
    assert parse("write a program of merge sort in C").tool == "generate_program"


def test_program_parser_supports_python_and_rejects_unknown():
    assert parse("create a program for fibonacci in Python").arguments["language"] == "python"
    with pytest.raises(ValueError):
        parse("write a program for merge sort in Rust")


def test_llm_json_parser_accepts_fences_and_rejects_non_object():
    assert _parse_json('```json\n{"ok": true}\n```') == {"ok": True}
    with pytest.raises(LLMError):
        _parse_json("[]")


def test_c_workflow_compiles_runs_and_opens(tmp_path, monkeypatch):
    monkeypatch.setattr(coding, "WORKSPACE", tmp_path / "LuciferProjects")

    class FakeClient:
        def generate_program(self, request, language, repair_context=""):
            return {
                "project_name": "Merge Sort",
                "file_name": "Merge_Sort.c",
                "code": '#include <stdio.h>\nint main(void) { puts("sorted"); return 0; }\n',
                "summary": "Prints a sorted-result marker.",
            }

    workflow = CodingWorkflow(ApplicationRegistry("Linux"), FakeClient())
    opened = []
    monkeypatch.setattr(workflow, "_open_project", opened.append)
    result = workflow.generate_program("merge sort", "c")
    assert result.ok
    assert result.code == "PROGRAM_VERIFIED"
    assert "sorted" in result.data["output"]
    assert opened == [tmp_path / "LuciferProjects" / "Merge_Sort"]
    assert (opened[0] / "Merge_Sort.c").is_file()


def test_c_workflow_repairs_once_after_compile_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(coding, "WORKSPACE", tmp_path / "LuciferProjects")
    calls = []

    class FakeClient:
        def generate_program(self, request, language, repair_context=""):
            calls.append(repair_context)
            code = "int main(void) {\n" if len(calls) == 1 else "int main(void) { return 0; }\n"
            return {
                "project_name": "Repair",
                "file_name": "Repair.c",
                "code": code,
                "summary": "repair",
            }

    workflow = CodingWorkflow(ApplicationRegistry("Linux"), FakeClient())
    monkeypatch.setattr(workflow, "_open_project", lambda project: None)
    result = workflow.generate_program("a tiny C program", "c")
    assert result.ok
    assert len(calls) == 2
    assert calls[1]


def test_generated_source_and_path_are_restricted(tmp_path, monkeypatch):
    monkeypatch.setattr(coding, "WORKSPACE", tmp_path / "LuciferProjects")

    class FakeClient:
        def generate_program(self, *args, **kwargs):
            return {
                "project_name": "../escape",
                "file_name": "bad.c",
                "code": 'system("rm");',
                "summary": "bad",
            }

    workflow = CodingWorkflow(ApplicationRegistry("Linux"), FakeClient())
    result = workflow.generate_program("bad", "c")
    assert not result.ok
    assert result.code == "CODE_WORKFLOW_FAILED"
    assert not (tmp_path / "escape").exists()
