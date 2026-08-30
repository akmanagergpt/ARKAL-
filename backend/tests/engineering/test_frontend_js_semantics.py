from __future__ import annotations

from arkali.engineering.factory.frontend_js_semantics import (
    _all_function_definitions,
    _function_parameters,
    _function_parameters_across_files,
)


class TestFunctionParameters:
    def test_a_plain_function_declaration(self) -> None:
        source = "async function updateStudent(id, name, email) { ... }\n"
        assert _function_parameters("updateStudent", source) == ("id", "name", "email")

    def test_a_const_arrow_function(self) -> None:
        source = "const createStudent = (name, email) => { ... };\n"
        assert _function_parameters("createStudent", source) == ("name", "email")

    def test_an_exported_const_arrow_function(self) -> None:
        """This exact shape is the real, confirmed inconsistency this
        module fixes: `frontend_callback_arity_preflight._function_
        definition_params` (before consolidation) never recognized an
        `export const name = (...) =>` declaration, while `frontend_
        mutation_contract._function_params` did -- two implementations of
        "find this function's real parameters" silently disagreeing."""
        source = "export const updateStudent = (id, name, email) => { ... };\n"
        assert _function_parameters("updateStudent", source) == ("id", "name", "email")

    def test_an_async_arrow_function(self) -> None:
        source = "const createTask = async (title, due_date) => { ... };\n"
        assert _function_parameters("createTask", source) == ("title", "due_date")

    def test_a_destructured_parameter_is_unresolvable_not_miscounted(self) -> None:
        source = "function updateStudent({ id, name, email }) { ... }\n"
        assert _function_parameters("updateStudent", source) is None

    def test_an_array_pattern_parameter_is_unresolvable(self) -> None:
        source = "const f = ([a, b]) => { ... };\n"
        assert _function_parameters("f", source) is None

    def test_a_name_not_defined_in_source_is_none(self) -> None:
        assert _function_parameters("updateStudent", "const other = () => {};\n") is None

    def test_zero_arity_is_a_real_empty_tuple_not_none(self) -> None:
        source = "function reset() { ... }\n"
        assert _function_parameters("reset", source) == ()


class TestFunctionParametersAcrossFiles:
    def test_finds_the_definition_in_a_different_file(self) -> None:
        files = {
            "frontend/src/App.js": "<StudentForm onSubmit={updateStudent} />",
            "frontend/src/apiClient.js": "export function updateStudent(id, name) {}\n",
        }
        assert _function_parameters_across_files("updateStudent", files) == ("id", "name")

    def test_none_when_no_file_defines_it(self) -> None:
        files = {"frontend/src/App.js": "<StudentForm onSubmit={updateStudent} />"}
        assert _function_parameters_across_files("updateStudent", files) is None


class TestAllFunctionDefinitions:
    def test_extracts_every_real_function_in_one_file(self) -> None:
        source = (
            "export function createStudent(name, email) {}\n"
            "const updateStudent = (id, name, email) => {};\n"
            "async function deleteStudent(id) {}\n"
        )
        found = _all_function_definitions(source)
        assert found == {
            "createStudent": ("name", "email"),
            "updateStudent": ("id", "name", "email"),
            "deleteStudent": ("id",),
        }

    def test_skips_a_destructured_definition_rather_than_miscounting(self) -> None:
        source = "function f({ id, name }) {}\nfunction g(a, b) {}\n"
        assert _all_function_definitions(source) == {"g": ("a", "b")}
