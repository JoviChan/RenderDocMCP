"""
RenderDoc API Facade
Provides thread-safe access to RenderDoc's ReplayController and CaptureContext.
Uses BlockInvoke to marshal calls to the replay thread.
"""

from .services import (
    CaptureManager,
    ActionService,
    SearchService,
    ResourceService,
    PipelineService,
)


class RenderDocFacade:
    """
    Facade for RenderDoc API access.

    This class delegates all operations to specialized service classes:
    - CaptureManager: Capture management (status, list, open)
    - ActionService: Draw call / action operations
    - SearchService: Reverse lookup searches
    - ResourceService: Texture and buffer data
    - PipelineService: Pipeline state and shader info
    """

    def __init__(self, ctx):
        """
        Initialize facade with CaptureContext.

        Args:
            ctx: The pyrenderdoc CaptureContext from register()
        """
        self.ctx = ctx

        # Initialize service classes
        self._capture = CaptureManager(ctx, self._invoke)
        self._action = ActionService(ctx, self._invoke)
        self._search = SearchService(ctx, self._invoke)
        self._resource = ResourceService(ctx, self._invoke)
        self._pipeline = PipelineService(ctx, self._invoke)

    def _invoke(self, callback):
        """Invoke callback on replay thread via BlockInvoke"""
        self.ctx.Replay().BlockInvoke(callback)

    # ==================== Capture Management ====================

    def get_capture_status(self):
        """Check if a capture is loaded and get API info"""
        return self._capture.get_capture_status()

    def list_captures(self, directory):
        """List all .rdc files in the specified directory"""
        return self._capture.list_captures(directory)

    def open_capture(self, capture_path):
        """Open a capture file in RenderDoc"""
        return self._capture.open_capture(capture_path)

    # ==================== Draw Call / Action Operations ====================

    def get_draw_calls(
        self,
        include_children=True,
        marker_filter=None,
        exclude_markers=None,
        event_id_min=None,
        event_id_max=None,
        only_actions=False,
        flags_filter=None,
    ):
        """Get all draw calls/actions in the capture with optional filtering"""
        return self._action.get_draw_calls(
            include_children=include_children,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
            event_id_min=event_id_min,
            event_id_max=event_id_max,
            only_actions=only_actions,
            flags_filter=flags_filter,
        )

    def get_frame_summary(self):
        """Get a summary of the current capture frame"""
        return self._action.get_frame_summary()

    def get_draw_call_details(self, event_id):
        """Get detailed information about a specific draw call"""
        return self._action.get_draw_call_details(event_id)

    def get_action_timings(self, event_ids=None, marker_filter=None, exclude_markers=None):
        """Get GPU timing information for actions"""
        return self._action.get_action_timings(
            event_ids=event_ids,
            marker_filter=marker_filter,
            exclude_markers=exclude_markers,
        )

    # ==================== Search Operations ====================

    def find_draws_by_shader(self, shader_name, stage=None):
        """Find all draw calls using a shader with the given name (partial match)"""
        return self._search.find_draws_by_shader(shader_name, stage)

    def find_draws_by_texture(self, texture_name):
        """Find all draw calls using a texture with the given name (partial match)"""
        return self._search.find_draws_by_texture(texture_name)

    def find_draws_by_resource(self, resource_id):
        """Find all draw calls using a specific resource ID (exact match)"""
        return self._search.find_draws_by_resource(resource_id)

    # ==================== Resource Operations ====================

    def get_buffer_contents(self, resource_id, offset=0, length=0):
        """Get buffer data"""
        return self._resource.get_buffer_contents(resource_id, offset, length)

    def read_buffer_typed(self, resource_id, offset=0, count=64,
                           data_type="float32", components=4):
        """Parse a buffer as a typed flat array (float32/uint16/...)."""
        return self._resource.read_buffer_typed(
            resource_id, offset, count, data_type, components
        )

    def get_texture_info(self, resource_id):
        """Get texture metadata"""
        return self._resource.get_texture_info(resource_id)

    def get_texture_data(self, resource_id, mip=0, slice=0, sample=0, depth_slice=None):
        """Get texture pixel data"""
        return self._resource.get_texture_data(resource_id, mip, slice, sample, depth_slice)

    def list_textures(self, name_filter=None):
        """List every texture in the capture."""
        return self._resource.list_textures(name_filter)

    def list_buffers(self, name_filter=None):
        """List every buffer in the capture."""
        return self._resource.list_buffers(name_filter)

    # ==================== Pipeline Operations ====================

    def get_shader_info(self, event_id, stage):
        """Get shader information for a specific stage"""
        return self._pipeline.get_shader_info(event_id, stage)

    def get_pipeline_state(self, event_id, include_cbuffer_values=True):
        """Get full pipeline state at an event"""
        return self._pipeline.get_pipeline_state(event_id, include_cbuffer_values)

    def get_cbuffer_values(self, event_id, stage="pixel", cbuffer_slot=None,
                           expand_depth=2, member_offset=0, member_limit=-1):
        """Read constant-buffer / uniform-buffer values for a draw call."""
        return self._pipeline.get_cbuffer_values(
            event_id, stage, cbuffer_slot, expand_depth, member_offset, member_limit
        )

    def expand_cbuffer_member(self, event_id, cbuffer_slot, member_path,
                              stage="pixel", expand_depth=2, member_limit=-1):
        """Drill into a deep cbuffer member by dotted/index path."""
        return self._pipeline.expand_cbuffer_member(
            event_id, cbuffer_slot, member_path, stage, expand_depth, member_limit
        )

    def get_shader_resources(self, event_id, stage):
        """One-shot dump of every binding for a given shader stage."""
        return self._pipeline.get_shader_resources(event_id, stage)

    # ==================== Action Extras ====================

    def get_dispatches(self, event_id_min=None, event_id_max=None, marker_filter=None):
        """List Compute Dispatches in the capture."""
        return self._action.get_dispatches(event_id_min, event_id_max, marker_filter)

    def get_pass_drawcalls(self, event_id):
        """Get all draw calls within the same render pass as ``event_id``."""
        return self._action.get_pass_drawcalls(event_id)

    def detect_engine(self):
        """Heuristic engine detection from marker patterns."""
        return self._action.detect_engine()

    def analyze_rdc(self):
        """Comprehensive frame analysis."""
        return self._action.analyze_rdc()

    def get_frame_hierarchy(self, max_depth=3):
        """Marker-only tree."""
        return self._action.get_frame_hierarchy(max_depth)

    def search_actions(self, name_pattern=None, marker_filter=None,
                       event_id_min=None, event_id_max=None, flags=None, limit=200):
        """Flexible action search."""
        return self._action.search_actions(
            name_pattern, marker_filter, event_id_min, event_id_max, flags, limit
        )

    def get_drawcall_summary(self, event_id_min=None, event_id_max=None,
                              marker_filter=None, limit=500):
        """Concise per-draw rows."""
        return self._action.get_drawcall_summary(
            event_id_min, event_id_max, marker_filter, limit
        )

    def get_drawcall_stats(self):
        """Aggregate draw-call statistics."""
        return self._action.get_drawcall_stats()

    def get_all_passes(self):
        """List every render pass."""
        return self._action.get_all_passes()

    def get_buffer_operations(self, event_id_min=None, event_id_max=None):
        """Copy/Resolve/GenMips/Clear events."""
        return self._action.get_buffer_operations(event_id_min, event_id_max)

    # ==================== Resource Stats / Search ====================

    def get_resource_overview(self):
        """High-level resource summary."""
        return self._resource.get_resource_overview()

    def get_texture_stats(self, top_n=10):
        """Texture distribution stats."""
        return self._resource.get_texture_stats(top_n)

    def get_buffer_stats(self, top_n=10):
        """Buffer distribution stats."""
        return self._resource.get_buffer_stats(top_n)

    def search_texture(self, name=None, format=None, min_width=None,
                       min_height=None, limit=200):
        """Find textures by name / format / dimensions."""
        return self._resource.search_texture(
            name, format, min_width, min_height, limit
        )

    def search_buffer(self, resource_id, target_value, data_type="float32",
                       components=1, tolerance=1e-4, max_results=20,
                       offset=0, length=0):
        """Locate occurrences of a numeric value inside a buffer."""
        return self._resource.search_buffer(
            resource_id, target_value, data_type, components, tolerance,
            max_results, offset, length,
        )

    # ==================== Shader Disassembly / Decompilation ====================

    def list_disassembly_targets(self):
        """Available disassembly targets."""
        return self._pipeline.list_disassembly_targets()

    def disassemble_shader(self, event_id, stage, target=None):
        """Get raw disassembly with target selection."""
        return self._pipeline.disassemble_shader(event_id, stage, target)

    def decompile_shader(self, event_id, stage, language="hlsl"):
        """Decompile to HLSL/GLSL."""
        return self._pipeline.decompile_shader(event_id, stage, language)

    # ==================== Pixel History ====================

    def get_pixel_history(self, resource_id, x, y, sub_resource=None):
        """Get pixel modification history."""
        return self._pipeline.get_pixel_history(resource_id, x, y, sub_resource)

    # ==================== Shader Debug ====================

    def debug_pixel_shader(self, event_id, x, y, sample=0, primitive=None):
        return self._pipeline.debug_pixel_shader(event_id, x, y, sample, primitive)

    def step_shader_debugger(self, session_id, step_count=1):
        return self._pipeline.step_shader_debugger(session_id, step_count)

    def get_shader_state(self, session_id):
        return self._pipeline.get_shader_state(session_id)

    def free_shader_debugger(self, session_id):
        return self._pipeline.free_shader_debugger(session_id)

    # ==================== Shader Edit ====================

    def apply_shader_edit(self, event_id, stage, source_code, language="hlsl"):
        return self._pipeline.apply_shader_edit(event_id, stage, source_code, language)

    def remove_shader_edit(self, event_id, stage):
        return self._pipeline.remove_shader_edit(event_id, stage)

    # ==================== Export ====================

    def export_texture(self, resource_id, output_path, mip=0, slice_idx=0, sample=0):
        return self._resource.export_texture(resource_id, output_path, mip, slice_idx, sample)

    def export_buffer(self, resource_id, output_path, offset=0, length=0):
        return self._resource.export_buffer(resource_id, output_path, offset, length)

    # ==================== RDG / Issues / Exec ====================

    def generate_rdg_flowchart(self, format="mermaid"):
        return self._action.generate_rdg_flowchart(format)

    def find_overlay_issues(self):
        return self._action.find_overlay_issues()

    def execute_python(self, code):
        return self._action.execute_python(code)
