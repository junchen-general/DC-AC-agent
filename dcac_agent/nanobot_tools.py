"""Only project tools are exposed to Nanobot; no shell or arbitrary-code tools."""
import asyncio
import json


def build_tools(service, job, schemas):
    from nanobot.agent.tools import Tool, tool_parameters

    result = []
    for schema in schemas:
        definition = schema["function"]

        def make_tool(definition):
            @tool_parameters(definition["parameters"])
            class ProjectTool(Tool):
                @property
                def name(self):
                    return definition["name"]

                @property
                def description(self):
                    return definition["description"]

                @property
                def read_only(self):
                    return self.name in {"get_design", "inspect_environment", "compare_runs", "get_multiphysics_results"}

                async def execute(self, **kwargs):
                    try:
                        value = await asyncio.to_thread(service._tool, job, self.name, kwargs)
                    except InterruptedError:
                        raise asyncio.CancelledError()
                    except Exception as exc:
                        # Provider secrets cannot occur in project tool parameters/results.
                        value = {"ok": False, "error": str(exc)}
                        service._emit(job, "error", self.name + " 失败", value)
                    return json.dumps(value, ensure_ascii=False, allow_nan=False)
            return ProjectTool()

        result.append(make_tool(definition))
    return result
