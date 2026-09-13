from __future__ import annotations

from arkali.engineering.factory.frontend_js_semantics import (
    _all_function_definitions,
    _commonjs_alias_export_names,
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


class TestCommonjsAliasExportNames:
    """F-0101 (`FRONTEND_UI_EDIT_EXPORT_MISDETECTION_AND_LABEL_HINT_GAP`,
    real evidence: `factory-goal-mtz6bst2-myhr15`'s own `apiClient.js`):
    `const api = {...}; module.exports = api;` is a real, statically-
    provable CommonJS re-export idiom the pre-existing `module.exports =
    { name, ... };` regex (`frontend_ux_preflight._COMMONJS_EXPORTS_
    BLOCK`) never recognized, since the object literal sits on the
    declaration line, not the `module.exports =` line itself."""

    def test_b_const_alias_with_shorthand_properties(self) -> None:
        source = (
            "const api = {\n"
            "  foo,\n"
            "  bar\n"
            "};\n"
            "module.exports = api;\n"
        )
        assert _commonjs_alias_export_names(source) == frozenset({"foo", "bar"})

    def test_c_let_alias_works(self) -> None:
        source = "let api = {\n  foo,\n  bar\n};\nmodule.exports = api;\n"
        assert _commonjs_alias_export_names(source) == frozenset({"foo", "bar"})

    def test_d_var_alias_works(self) -> None:
        source = "var api = {\n  foo,\n  bar\n};\nmodule.exports = api;\n"
        assert _commonjs_alias_export_names(source) == frozenset({"foo", "bar"})

    def test_f_explicit_key_value_properties(self) -> None:
        source = (
            "const api = {\n"
            "  foo: fooImpl,\n"
            "  bar: barImpl\n"
            "};\n"
            "module.exports = api;\n"
        )
        assert _commonjs_alias_export_names(source) == frozenset({"foo", "bar"})

    def test_g_nested_braces_in_property_values_do_not_truncate_extraction(self) -> None:
        """The exact real shape this finding's own evidence has: each
        property's own value is an async arrow function with its own
        nested `{...}` body (a real `try`/`catch`), so a naive `[^}]*`
        capture -- correct only for a flat, brace-free property list --
        would stop at the first nested closing brace and silently miss
        every property declared after it."""
        source = (
            "const api = {\n"
            "  getThing: async () => {\n"
            "    try {\n"
            "      return await axios.get('/thing');\n"
            "    } catch (error) {\n"
            "      throw new Error('failed');\n"
            "    }\n"
            "  },\n"
            "  updateThing: async (id, data) => {\n"
            "    try {\n"
            "      return await axios.put(`/thing/${id}`, data);\n"
            "    } catch (error) {\n"
            "      throw new Error('failed');\n"
            "    }\n"
            "  }\n"
            "};\n"
            "module.exports = api;\n"
        )
        assert _commonjs_alias_export_names(source) == frozenset({"getThing", "updateThing"})

    def test_h_an_unresolved_identifier_remains_unsupported(self) -> None:
        """`module.exports = someImportedOrUnknownIdentifier;` with no
        local object-literal declaration of that name anywhere in the
        file -- never guessed."""
        source = "module.exports = someImportedOrUnknownIdentifier;\n"
        assert _commonjs_alias_export_names(source) == frozenset()

    def test_h_a_multi_hop_alias_remains_unsupported(self) -> None:
        """`const a = b; module.exports = a;` -- `a` itself is never
        declared as an object literal, only re-bound from another name;
        remains conservative rather than following the alias chain."""
        source = "const b = { foo, bar };\nconst a = b;\nmodule.exports = a;\n"
        assert _commonjs_alias_export_names(source) == frozenset()

    def test_i_a_locally_declared_object_never_exported_is_ignored(self) -> None:
        """A real local object literal that `module.exports` never
        references at all must contribute nothing -- only an identifier
        actually assigned to `module.exports` is ever resolved."""
        source = "const internalConfig = { retries, timeout };\nmodule.exports = {};\n"
        assert _commonjs_alias_export_names(source) == frozenset()

    def test_j_the_real_frozen_f0101_apiclient_fixture(self) -> None:
        """The exact real `apiClient.js` `factory-goal-mtz6bst2-myhr15`
        produced (F-0101's own historical evidence)."""
        source = (
            "const axios = require('axios');\n\n"
            "const API_BASE_URL = 'http://localhost:5000';\n\n"
            "const apiClient = {\n"
            "  getCustomers: async () => {\n"
            "    try {\n"
            "      const response = await axios.get(`${API_BASE_URL}/customers`);\n"
            "      return response.data;\n"
            "    } catch (error) {\n"
            "      throw new Error('Failed to fetch customers');\n"
            "    }\n"
            "  },\n\n"
            "  updateCustomer: async (id, customerData) => {\n"
            "    try {\n"
            "      const response = await axios.put(`${API_BASE_URL}/customers/${id}`, customerData);\n"
            "      return response.data;\n"
            "    } catch (error) {\n"
            "      throw new Error('Failed to update customer');\n"
            "    }\n"
            "  },\n\n"
            "  updateTicket: async (id, ticketData) => {\n"
            "    try {\n"
            "      const response = await axios.put(`${API_BASE_URL}/tickets/${id}`, ticketData);\n"
            "      return response.data;\n"
            "    } catch (error) {\n"
            "      throw new Error('Failed to update ticket');\n"
            "    }\n"
            "  }\n"
            "};\n\n"
            "module.exports = apiClient;\n"
        )
        names = _commonjs_alias_export_names(source)
        assert {"getCustomers", "updateCustomer", "updateTicket"} <= names
