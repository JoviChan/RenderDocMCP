"""
Request Handler for RenderDoc MCP Bridge
Routes incoming requests to appropriate facade methods.
"""

import traceback


class RequestHandler:
    """Handles incoming MCP bridge requests"""

    def __init__(self, facade):
        self.facade = facade
        self._methods = {
            "ping": self._handle_ping,
            "get_capture_status": self._handle_get_capture_status,
            "get_draw_calls": self._handle_get_draw_calls,
            "get_frame_summary": self._handle_get_frame_summary,
            "find_draws_by_shader": self._handle_find_draws_by_shader,
            "find_draws_by_texture": self._handle_find_draws_by_texture,
            "find_draws_by_resource": self._handle_find_draws_by_resource,
            "get_draw_call_details": self._handle_get_draw_call_details,
            "get_action_timings": self._handle_get_action_timings,
            "get_shader_info": self._handle_get_shader_info,
            "get_buffer_contents": self._handle_get_buffer_contents,
            "read_buffer_typed": self._handle_read_buffer_typed,
            "get_texture_info": self._handle_get_texture_info,
            "get_texture_data": self._handle_get_texture_data,
            "list_textures": self._handle_list_textures,
            "list_buffers": self._handle_list_buffers,
            "get_pipeline_state": self._handle_get_pipeline_state,
            "get_cbuffer_values": self._handle_get_cbuffer_values,
            "expand_cbuffer_member": self._handle_expand_cbuffer_member,
            "get_shader_resources": self._handle_get_shader_resources,
            "get_dispatches": self._handle_get_dispatches,
            "get_pass_drawcalls": self._handle_get_pass_drawcalls,
            "detect_engine": self._handle_detect_engine,
            "analyze_rdc": self._handle_analyze_rdc,
            "get_frame_hierarchy": self._handle_get_frame_hierarchy,
            "search_actions": self._handle_search_actions,
            "get_drawcall_summary": self._handle_get_drawcall_summary,
            "get_drawcall_stats": self._handle_get_drawcall_stats,
            "get_all_passes": self._handle_get_all_passes,
            "get_buffer_operations": self._handle_get_buffer_operations,
            "get_resource_overview": self._handle_get_resource_overview,
            "get_texture_stats": self._handle_get_texture_stats,
            "get_buffer_stats": self._handle_get_buffer_stats,
            "search_texture": self._handle_search_texture,
            "search_buffer": self._handle_search_buffer,
            "list_disassembly_targets": self._handle_list_disassembly_targets,
            "disassemble_shader": self._handle_disassemble_shader,
            "decompile_shader": self._handle_decompile_shader,
            "get_pixel_history": self._handle_get_pixel_history,
            "debug_pixel_shader": self._handle_debug_pixel_shader,
            "step_shader_debugger": self._handle_step_shader_debugger,
            "get_shader_state": self._handle_get_shader_state,
            "free_shader_debugger": self._handle_free_shader_debugger,
            "apply_shader_edit": self._handle_apply_shader_edit,
            "remove_shader_edit": self._handle_remove_shader_edit,
            "export_texture": self._handle_export_texture,
            "export_buffer": self._handle_export_buffer,
            "generate_rdg_flowchart": self._handle_generate_rdg_flowchart,
            "find_overlay_issues": self._handle_find_overlay_issues,
            "execute_python": self._handle_execute_python,
            "list_captures": self._handle_list_captures,
            "open_capture": self._handle_open_capture,
        }

    def handle(self, request):
        """Handle a request and return response"""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method not in self._methods:
                return self._error_response(
                    request_id, -32601, "Method not found: %s" % method
                )

            result = self._methods[method](params)
            return {"id": request_id, "result": result}

        except ValueError as e:
            return self._error_response(request_id, -32602, str(e))
        except Exception as e:
            traceback.print_exc()
            return self._error_response(request_id, -32000, str(e))

    def _error_response(self, request_id, code, message):
        """Create an error response"""
        return {"id": request_id, "error": {"code": code, "message": message}}

    def _handle_ping(self, params):
        """Handle ping request"""
        return {"status": "ok", "message": "pong"}

    def _handle_get_capture_status(self, params):
        """Handle get_capture_status request"""
        return self.facade.get_capture_status()

    def _handle_get_draw_calls(self, params):
        """Handle get_draw_calls request"""
        include_children = params.get("include_children", True)
        marker_filter = params.get("marker_filter")
        exclude_markers = params.get("exclude_markers")
        event_id_min = params.get("event_id_min")
        event_id_max = params.get("event_id_max")
        only_actions = params.get("only_actions", False)
        flags_filter = params.get("flags_filter")
        return self.facade.get_draw_calls(
            include_children=include_children,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
            event_id_min=event_id_min,
            event_id_max=event_id_max,
            only_actions=only_actions,
            flags_filter=flags_filter,
        )

    def _handle_get_frame_summary(self, params):
        """Handle get_frame_summary request"""
        return self.facade.get_frame_summary()

    def _handle_find_draws_by_shader(self, params):
        """Handle find_draws_by_shader request"""
        shader_name = params.get("shader_name")
        if shader_name is None:
            raise ValueError("shader_name is required")
        stage = params.get("stage")
        return self.facade.find_draws_by_shader(shader_name, stage)

    def _handle_find_draws_by_texture(self, params):
        """Handle find_draws_by_texture request"""
        texture_name = params.get("texture_name")
        if texture_name is None:
            raise ValueError("texture_name is required")
        return self.facade.find_draws_by_texture(texture_name)

    def _handle_find_draws_by_resource(self, params):
        """Handle find_draws_by_resource request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.find_draws_by_resource(resource_id)

    def _handle_get_draw_call_details(self, params):
        """Handle get_draw_call_details request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_draw_call_details(int(event_id))

    def _handle_get_action_timings(self, params):
        """Handle get_action_timings request"""
        event_ids = params.get("event_ids")
        marker_filter = params.get("marker_filter")
        exclude_markers = params.get("exclude_markers")
        return self.facade.get_action_timings(
            event_ids=event_ids,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
        )

    def _handle_get_shader_info(self, params):
        """Handle get_shader_info request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None:
            raise ValueError("event_id is required")
        if stage is None:
            raise ValueError("stage is required")
        return self.facade.get_shader_info(int(event_id), stage)

    def _handle_get_buffer_contents(self, params):
        """Handle get_buffer_contents request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        offset = params.get("offset", 0)
        length = params.get("length", 0)
        return self.facade.get_buffer_contents(resource_id, offset, length)

    def _handle_get_texture_info(self, params):
        """Handle get_texture_info request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        return self.facade.get_texture_info(resource_id)

    def _handle_get_texture_data(self, params):
        """Handle get_texture_data request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        mip = params.get("mip", 0)
        slice_idx = params.get("slice", 0)
        sample = params.get("sample", 0)
        depth_slice = params.get("depth_slice")  # None = full volume
        return self.facade.get_texture_data(resource_id, mip, slice_idx, sample, depth_slice)

    def _handle_get_pipeline_state(self, params):
        """Handle get_pipeline_state request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        include_cbuffer_values = params.get("include_cbuffer_values", True)
        return self.facade.get_pipeline_state(int(event_id), include_cbuffer_values)

    def _handle_get_cbuffer_values(self, params):
        """Handle get_cbuffer_values request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        stage = params.get("stage", "pixel")
        cbuffer_slot = params.get("cbuffer_slot")
        if cbuffer_slot is not None:
            cbuffer_slot = int(cbuffer_slot)
        expand_depth = int(params.get("expand_depth", 2))
        member_offset = int(params.get("member_offset", 0))
        member_limit = int(params.get("member_limit", -1))
        return self.facade.get_cbuffer_values(
            int(event_id), stage, cbuffer_slot, expand_depth, member_offset, member_limit
        )

    def _handle_expand_cbuffer_member(self, params):
        """Handle expand_cbuffer_member request"""
        event_id = params.get("event_id")
        cbuffer_slot = params.get("cbuffer_slot")
        member_path = params.get("member_path")
        if event_id is None or cbuffer_slot is None or member_path is None:
            raise ValueError("event_id, cbuffer_slot, member_path are required")
        stage = params.get("stage", "pixel")
        expand_depth = int(params.get("expand_depth", 2))
        member_limit = int(params.get("member_limit", -1))
        return self.facade.expand_cbuffer_member(
            int(event_id), int(cbuffer_slot), str(member_path),
            stage, expand_depth, member_limit,
        )

    def _handle_get_shader_resources(self, params):
        """Handle get_shader_resources request"""
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None or stage is None:
            raise ValueError("event_id and stage are required")
        return self.facade.get_shader_resources(int(event_id), stage)

    def _handle_read_buffer_typed(self, params):
        """Handle read_buffer_typed request"""
        resource_id = params.get("resource_id")
        if resource_id is None:
            raise ValueError("resource_id is required")
        offset = int(params.get("offset", 0))
        count = int(params.get("count", 64))
        data_type = params.get("data_type", "float32")
        components = int(params.get("components", 4))
        return self.facade.read_buffer_typed(
            resource_id, offset, count, data_type, components
        )

    def _handle_list_textures(self, params):
        """Handle list_textures request"""
        return self.facade.list_textures(params.get("name_filter"))

    def _handle_list_buffers(self, params):
        """Handle list_buffers request"""
        return self.facade.list_buffers(params.get("name_filter"))

    def _handle_get_dispatches(self, params):
        """Handle get_dispatches request"""
        return self.facade.get_dispatches(
            event_id_min=params.get("event_id_min"),
            event_id_max=params.get("event_id_max"),
            marker_filter=params.get("marker_filter"),
        )

    def _handle_get_pass_drawcalls(self, params):
        """Handle get_pass_drawcalls request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        return self.facade.get_pass_drawcalls(int(event_id))

    def _handle_detect_engine(self, params):
        """Handle detect_engine request"""
        return self.facade.detect_engine()

    def _handle_analyze_rdc(self, params):
        return self.facade.analyze_rdc()

    def _handle_get_frame_hierarchy(self, params):
        return self.facade.get_frame_hierarchy(int(params.get("max_depth", 3)))

    def _handle_search_actions(self, params):
        return self.facade.search_actions(
            name_pattern=params.get("name_pattern"),
            marker_filter=params.get("marker_filter"),
            event_id_min=params.get("event_id_min"),
            event_id_max=params.get("event_id_max"),
            flags=params.get("flags"),
            limit=int(params.get("limit", 200)),
        )

    def _handle_get_drawcall_summary(self, params):
        return self.facade.get_drawcall_summary(
            event_id_min=params.get("event_id_min"),
            event_id_max=params.get("event_id_max"),
            marker_filter=params.get("marker_filter"),
            limit=int(params.get("limit", 500)),
        )

    def _handle_get_drawcall_stats(self, params):
        return self.facade.get_drawcall_stats()

    def _handle_get_all_passes(self, params):
        return self.facade.get_all_passes()

    def _handle_get_buffer_operations(self, params):
        return self.facade.get_buffer_operations(
            event_id_min=params.get("event_id_min"),
            event_id_max=params.get("event_id_max"),
        )

    def _handle_get_resource_overview(self, params):
        return self.facade.get_resource_overview()

    def _handle_get_texture_stats(self, params):
        return self.facade.get_texture_stats(int(params.get("top_n", 10)))

    def _handle_get_buffer_stats(self, params):
        return self.facade.get_buffer_stats(int(params.get("top_n", 10)))

    def _handle_search_texture(self, params):
        return self.facade.search_texture(
            name=params.get("name"),
            format=params.get("format"),
            min_width=params.get("min_width"),
            min_height=params.get("min_height"),
            limit=int(params.get("limit", 200)),
        )

    def _handle_search_buffer(self, params):
        resource_id = params.get("resource_id")
        target_value = params.get("target_value")
        if resource_id is None or target_value is None:
            raise ValueError("resource_id and target_value are required")
        return self.facade.search_buffer(
            resource_id=resource_id,
            target_value=target_value,
            data_type=params.get("data_type", "float32"),
            components=int(params.get("components", 1)),
            tolerance=float(params.get("tolerance", 1e-4)),
            max_results=int(params.get("max_results", 20)),
            offset=int(params.get("offset", 0)),
            length=int(params.get("length", 0)),
        )

    def _handle_list_disassembly_targets(self, params):
        return self.facade.list_disassembly_targets()

    def _handle_disassemble_shader(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None or stage is None:
            raise ValueError("event_id and stage are required")
        return self.facade.disassemble_shader(int(event_id), stage, params.get("target"))

    def _handle_decompile_shader(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None or stage is None:
            raise ValueError("event_id and stage are required")
        return self.facade.decompile_shader(
            int(event_id), stage, params.get("language", "hlsl")
        )

    def _handle_get_pixel_history(self, params):
        resource_id = params.get("resource_id")
        x = params.get("x")
        y = params.get("y")
        if resource_id is None or x is None or y is None:
            raise ValueError("resource_id, x, y are required")
        return self.facade.get_pixel_history(resource_id, int(x), int(y))

    def _handle_debug_pixel_shader(self, params):
        event_id = params.get("event_id")
        x = params.get("x")
        y = params.get("y")
        if event_id is None or x is None or y is None:
            raise ValueError("event_id, x, y are required")
        return self.facade.debug_pixel_shader(
            int(event_id), int(x), int(y),
            int(params.get("sample", 0)),
            params.get("primitive"),
        )

    def _handle_step_shader_debugger(self, params):
        session_id = params.get("session_id")
        if session_id is None:
            raise ValueError("session_id is required")
        return self.facade.step_shader_debugger(session_id, int(params.get("step_count", 1)))

    def _handle_get_shader_state(self, params):
        session_id = params.get("session_id")
        if session_id is None:
            raise ValueError("session_id is required")
        return self.facade.get_shader_state(session_id)

    def _handle_free_shader_debugger(self, params):
        session_id = params.get("session_id")
        if session_id is None:
            raise ValueError("session_id is required")
        return self.facade.free_shader_debugger(session_id)

    def _handle_apply_shader_edit(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        source_code = params.get("source_code")
        if event_id is None or stage is None or source_code is None:
            raise ValueError("event_id, stage, source_code are required")
        return self.facade.apply_shader_edit(
            int(event_id), stage, source_code, params.get("language", "hlsl")
        )

    def _handle_remove_shader_edit(self, params):
        event_id = params.get("event_id")
        stage = params.get("stage")
        if event_id is None or stage is None:
            raise ValueError("event_id and stage are required")
        return self.facade.remove_shader_edit(int(event_id), stage)

    def _handle_export_texture(self, params):
        resource_id = params.get("resource_id")
        output_path = params.get("output_path")
        if resource_id is None or output_path is None:
            raise ValueError("resource_id and output_path are required")
        return self.facade.export_texture(
            resource_id, output_path,
            int(params.get("mip", 0)),
            int(params.get("slice", 0)),
            int(params.get("sample", 0)),
        )

    def _handle_export_buffer(self, params):
        resource_id = params.get("resource_id")
        output_path = params.get("output_path")
        if resource_id is None or output_path is None:
            raise ValueError("resource_id and output_path are required")
        return self.facade.export_buffer(
            resource_id, output_path,
            int(params.get("offset", 0)),
            int(params.get("length", 0)),
        )

    def _handle_generate_rdg_flowchart(self, params):
        return self.facade.generate_rdg_flowchart(params.get("format", "mermaid"))

    def _handle_find_overlay_issues(self, params):
        return self.facade.find_overlay_issues()

    def _handle_execute_python(self, params):
        code = params.get("code")
        if code is None:
            raise ValueError("code is required")
        return self.facade.execute_python(code)

    def _handle_list_captures(self, params):
        """Handle list_captures request"""
        directory = params.get("directory")
        if directory is None:
            raise ValueError("directory is required")
        return self.facade.list_captures(directory)

    def _handle_open_capture(self, params):
        """Handle open_capture request"""
        capture_path = params.get("capture_path")
        if capture_path is None:
            raise ValueError("capture_path is required")
        return self.facade.open_capture(capture_path)
