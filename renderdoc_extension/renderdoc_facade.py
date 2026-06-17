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
