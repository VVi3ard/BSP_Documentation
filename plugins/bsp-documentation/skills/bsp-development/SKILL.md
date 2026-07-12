---
name: bsp-development
description: Use when implementing, changing, reviewing, or investigating 1C/BSL code that may use the 1C Standard Subsystems Library (BSP). Discover BSP APIs through the bundled BSP Documentation MCP, verify official method documentation, and inspect real calls in the bundled demo configuration before writing new BSP calls.
---

# BSP development

1. Determine the project's BSP version with `detect_bsp_version` before every documentation lookup.
2. For a new feature, call `discover_bsp_api_sections` with the development task. Inspect the selected subsystem with `get_bsp_api_section_map`.
3. Search only the selected group through `search_bsp` with `mode="development"`. Use `mode="override"` for extension callbacks.
4. Call `get_bsp_section` before writing a BSP method call. Treat this documentation as normative.
5. For new code, call `get_bsp_demo_location` and search the returned directory for the complete BSP symbol, such as `РаботаСФайлами.ДобавитьФайл`.
6. Read the enclosing BSL procedure. Follow `ОписаниеОповещения`, called procedures, client-server transitions, form commands and related managed-form files when the example is UI-driven.
7. Treat the demo configuration as an implementation example, not as a replacement for the official documentation. Adapt it to the target project instead of copying it blindly.

## Delegated BSP research

For an uncertain or multi-step BSP task, delegate only documentation retrieval and candidate ranking to a read-only research subagent before changing code. The subagent must call the MCP tools. It returns only:

- 3–5 ranked API candidates with a one-line reason;
- the recommended method and documented constraints;
- unresolved uncertainty.

Do not delegate a simple lookup when the exact BSP method is already known. Do not ask the research subagent to modify the target project or return raw MCP pages.

After the main agent selects a method, it must itself call `get_bsp_demo_location`, search the demo sources, and read the complete implementation scenario. Keep the selected procedure, its callbacks, UI links and client-server transitions in the main context: these details are required to adapt the method correctly. The main agent makes the final design choice and writes the code.

Keep retrieved context progressive: first navigation, then one method page, then only the selected demo procedure and its direct dependencies.
