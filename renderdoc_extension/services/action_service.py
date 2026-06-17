"""
Draw call / action operations service for RenderDoc.
"""

import renderdoc as rd

from ..utils import Serializers, Helpers


class ActionService:
    """Draw call / action operations service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

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
        """
        Get all draw calls/actions in the capture with optional filtering.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"actions": []}

        def callback(controller):
            root_actions = controller.GetRootActions()
            structured_file = controller.GetStructuredFile()
            result["actions"] = Serializers.serialize_actions(
                root_actions,
                structured_file,
                include_children,
                marker_filter=marker_filter,
                exclude_markers=exclude_markers,
                event_id_min=event_id_min,
                event_id_max=event_id_max,
                only_actions=only_actions,
                flags_filter=flags_filter,
            )

        self._invoke(callback)
        return result

    def get_frame_summary(self):
        """
        Get a summary of the current capture frame.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"summary": None}

        def callback(controller):
            root_actions = controller.GetRootActions()
            structured_file = controller.GetStructuredFile()
            api = controller.GetAPIProperties().pipelineType

            # Statistics counters
            stats = {
                "draw_calls": 0,
                "dispatches": 0,
                "clears": 0,
                "copies": 0,
                "presents": 0,
                "markers": 0,
            }
            total_actions = [0]

            def count_actions(actions):
                for action in actions:
                    total_actions[0] += 1
                    flags = action.flags

                    if flags & rd.ActionFlags.Drawcall:
                        stats["draw_calls"] += 1
                    if flags & rd.ActionFlags.Dispatch:
                        stats["dispatches"] += 1
                    if flags & rd.ActionFlags.Clear:
                        stats["clears"] += 1
                    if flags & rd.ActionFlags.Copy:
                        stats["copies"] += 1
                    if flags & rd.ActionFlags.Present:
                        stats["presents"] += 1
                    if flags & (rd.ActionFlags.PushMarker | rd.ActionFlags.SetMarker):
                        stats["markers"] += 1

                    if action.children:
                        count_actions(action.children)

            count_actions(root_actions)

            # Top-level markers
            top_markers = []
            for action in root_actions:
                if action.flags & rd.ActionFlags.PushMarker:
                    child_count = Helpers.count_children(action)
                    top_markers.append({
                        "name": action.GetName(structured_file),
                        "event_id": action.eventId,
                        "child_count": child_count,
                    })

            # Resource counts
            textures = controller.GetTextures()
            buffers = controller.GetBuffers()

            result["summary"] = {
                "api": str(api),
                "total_actions": total_actions[0],
                "statistics": stats,
                "top_level_markers": top_markers,
                "resource_counts": {
                    "textures": len(textures),
                    "buffers": len(buffers),
                },
            }

        self._invoke(callback)
        return result["summary"]

    def get_draw_call_details(self, event_id):
        """Get detailed information about a specific draw call"""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"details": None, "error": None}

        def callback(controller):
            # Move to the event
            controller.SetFrameEvent(event_id, True)

            action = self.ctx.GetAction(event_id)
            if not action:
                result["error"] = "No action at event %d" % event_id
                return

            structured_file = controller.GetStructuredFile()

            details = {
                "event_id": action.eventId,
                "action_id": action.actionId,
                "name": action.GetName(structured_file),
                "flags": Serializers.serialize_flags(action.flags),
                "num_indices": action.numIndices,
                "num_instances": action.numInstances,
                "base_vertex": action.baseVertex,
                "vertex_offset": action.vertexOffset,
                "instance_offset": action.instanceOffset,
                "index_offset": action.indexOffset,
            }

            # Output resources
            outputs = []
            for i, output in enumerate(action.outputs):
                if output != rd.ResourceId.Null():
                    outputs.append({"index": i, "resource_id": str(output)})
            details["outputs"] = outputs

            if action.depthOut != rd.ResourceId.Null():
                details["depth_output"] = str(action.depthOut)

            result["details"] = details

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["details"]

    def get_action_timings(
        self,
        event_ids=None,
        marker_filter=None,
        exclude_markers=None,
    ):
        """
        Get GPU timing information for actions.

        Args:
            event_ids: Optional list of specific event IDs to get timings for.
                      If None, returns timings for all actions.
            marker_filter: Only include actions under markers containing this string.
            exclude_markers: Exclude actions under markers containing these strings.

        Returns:
            Dictionary with:
            - available: Whether GPU timing counters are supported
            - unit: Time unit (typically "seconds")
            - timings: List of {event_id, name, duration_seconds, duration_ms}
            - total_duration_ms: Sum of all durations
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"data": None, "error": None}

        def callback(controller):
            # Check if EventGPUDuration counter is available
            counters = controller.EnumerateCounters()
            if rd.GPUCounter.EventGPUDuration not in counters:
                result["data"] = {
                    "available": False,
                    "error": "GPU timing counters not supported on this capture",
                }
                return

            # Get counter description
            counter_desc = controller.DescribeCounter(rd.GPUCounter.EventGPUDuration)

            # Fetch timing data
            counter_results = controller.FetchCounters([rd.GPUCounter.EventGPUDuration])

            # Build event_id to timing map
            timing_map = {}
            target_counter = int(rd.GPUCounter.EventGPUDuration)
            for r in counter_results:
                if r.counter == target_counter:
                    # EventGPUDuration typically returns double
                    # Try to get the value in the most appropriate way
                    val = r.value.d  # double is the standard for duration
                    timing_map[r.eventId] = val

            # Get structured file for action names
            structured_file = controller.GetStructuredFile()
            root_actions = controller.GetRootActions()

            # Collect actions to report timings for
            timings = []
            total_duration = [0.0]

            def collect_timings(actions, parent_markers=None):
                if parent_markers is None:
                    parent_markers = []

                for action in actions:
                    action_name = action.GetName(structured_file)
                    current_markers = parent_markers[:]

                    # Track marker hierarchy
                    is_marker = bool(action.flags & (rd.ActionFlags.PushMarker | rd.ActionFlags.SetMarker))
                    if is_marker:
                        current_markers.append(action_name)

                    # Apply marker filter
                    if marker_filter:
                        marker_path = "/".join(current_markers)
                        if marker_filter.lower() not in marker_path.lower():
                            # Still recurse into children
                            if action.children:
                                collect_timings(action.children, current_markers)
                            continue

                    # Apply exclude filter
                    if exclude_markers:
                        skip = False
                        for exclude in exclude_markers:
                            for m in current_markers:
                                if exclude.lower() in m.lower():
                                    skip = True
                                    break
                            if skip:
                                break
                        if skip:
                            if action.children:
                                collect_timings(action.children, current_markers)
                            continue

                    # Check if we should include this event
                    event_id = action.eventId
                    include = True
                    if event_ids is not None:
                        include = event_id in event_ids

                    if include and event_id in timing_map:
                        duration_sec = timing_map[event_id]
                        duration_ms = duration_sec * 1000.0
                        timings.append({
                            "event_id": event_id,
                            "name": action_name,
                            "duration_seconds": duration_sec,
                            "duration_ms": duration_ms,
                        })
                        total_duration[0] += duration_ms

                    # Recurse into children
                    if action.children:
                        collect_timings(action.children, current_markers)

            collect_timings(root_actions)

            # Sort by event_id
            timings.sort(key=lambda x: x["event_id"])

            result["data"] = {
                "available": True,
                "unit": str(counter_desc.unit),
                "timings": timings,
                "total_duration_ms": total_duration[0],
                "count": len(timings),
            }

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def get_dispatches(self, event_id_min=None, event_id_max=None,
                       marker_filter=None):
        """List every Compute Dispatch in the capture (optionally filtered)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"dispatches": []}

        def callback(controller):
            structured = controller.GetStructuredFile()
            entries = []

            def visit(actions, marker_path):
                for a in actions:
                    name = a.GetName(structured)
                    flags = a.flags

                    is_push = flags & rd.ActionFlags.PushMarker
                    if is_push:
                        marker_path = marker_path + [name]

                    if flags & rd.ActionFlags.Dispatch:
                        ev = a.eventId
                        if event_id_min is not None and ev < event_id_min:
                            pass
                        elif event_id_max is not None and ev > event_id_max:
                            pass
                        elif marker_filter and not any(
                            marker_filter.lower() in m.lower() for m in marker_path
                        ):
                            pass
                        else:
                            entries.append({
                                "event_id": ev,
                                "name": name,
                                "dispatch_threads_x": a.dispatchDimension[0]
                                    if hasattr(a, "dispatchDimension") else None,
                                "dispatch_threads_y": a.dispatchDimension[1]
                                    if hasattr(a, "dispatchDimension") else None,
                                "dispatch_threads_z": a.dispatchDimension[2]
                                    if hasattr(a, "dispatchDimension") else None,
                                "marker_path": list(marker_path),
                            })

                    if a.children:
                        visit(a.children, marker_path)

                    if is_push:
                        marker_path = marker_path[:-1]

            visit(controller.GetRootActions(), [])
            result["dispatches"] = entries
            result["count"] = len(entries)

        self._invoke(callback)
        return result

    def get_pass_drawcalls(self, event_id):
        """Get every draw within the same render pass as ``event_id``.

        A "pass" is delimited by BeginPass/EndPass flags. The closest
        enclosing PushMarker chain is treated as the pass when no explicit
        pass boundary exists.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"pass": None, "draws": []}

        def callback(controller):
            structured = controller.GetStructuredFile()

            # Walk to find the nearest PushMarker that contains event_id.
            ancestor = None

            def find(actions, parent):
                nonlocal ancestor
                for a in actions:
                    is_push = a.flags & rd.ActionFlags.PushMarker
                    candidate = a if is_push else parent
                    if a.eventId == event_id:
                        ancestor = candidate
                        return True
                    if a.children:
                        if find(a.children, candidate):
                            return True
                return False

            find(controller.GetRootActions(), None)
            if ancestor is None:
                result["error"] = "No enclosing pass found for event %d" % event_id
                return

            # Collect draws under that ancestor (or all children if no ancestor).
            draws = []
            def collect(actions):
                for a in actions:
                    if a.flags & rd.ActionFlags.Drawcall:
                        draws.append({
                            "event_id": a.eventId,
                            "name": a.GetName(structured),
                            "num_indices": a.numIndices,
                            "num_instances": a.numInstances,
                        })
                    if a.children:
                        collect(a.children)

            collect(ancestor.children)
            result["pass"] = {
                "name": ancestor.GetName(structured),
                "event_id": ancestor.eventId,
            }
            result["draws"] = draws
            result["count"] = len(draws)

        self._invoke(callback)
        if "error" in result:
            raise ValueError(result["error"])
        return result

    def detect_engine(self):
        """Heuristic engine detection from marker names and resource patterns."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"engine": "unknown", "confidence": 0.0, "markers_seen": []}

        # Common signatures (substring, lowercased) -> engine name.
        signatures = [
            ("camera.render", "Unity"),
            ("uir.drawchain", "Unity"),
            ("ugui.rendering", "Unity"),
            ("renderforward.renderloopjob", "Unity"),
            ("playerendofframe", "Unity"),
            ("editorloop", "Unity"),
            ("scenecaptureviews", "Unreal"),
            ("rdg::", "Unreal"),
            ("basepass", "Unreal"),
            ("translucency", "Unreal"),
            ("postprocessing", "Unreal"),
            ("lumen", "Unreal"),
            ("nanite", "Unreal"),
            ("neox", "NeoX"),
            ("aurora", "NeoX"),
            ("mobile_branch", "NeoX"),
        ]

        scores = {}
        seen_markers = []

        def callback(controller):
            structured = controller.GetStructuredFile()
            roots = controller.GetRootActions()

            def visit(actions, depth=0):
                for a in actions:
                    if a.flags & (rd.ActionFlags.PushMarker | rd.ActionFlags.SetMarker):
                        name = a.GetName(structured) or ""
                        if depth < 3 and len(seen_markers) < 30:
                            seen_markers.append(name)
                        low = name.lower()
                        for sig, eng in signatures:
                            if sig in low:
                                scores[eng] = scores.get(eng, 0) + 1
                    if a.children:
                        visit(a.children, depth + 1)

            visit(roots)

        self._invoke(callback)

        if scores:
            best = max(scores.items(), key=lambda kv: kv[1])
            total = sum(scores.values())
            result["engine"] = best[0]
            result["confidence"] = best[1] / total
            result["scores"] = scores
        result["markers_seen"] = seen_markers
        return result

    # =================================================================
    # Frame analysis & search
    # =================================================================

    def analyze_rdc(self):
        """Comprehensive frame analysis: hierarchy, totals, top markers, resources."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"analysis": None}

        def callback(controller):
            roots = controller.GetRootActions()
            structured = controller.GetStructuredFile()
            api = controller.GetAPIProperties().pipelineType

            stats = {
                "draw_calls": 0, "dispatches": 0, "clears": 0,
                "copies": 0, "resolves": 0, "gen_mips": 0,
                "presents": 0, "markers": 0, "begin_pass": 0,
                "indexed_draws": 0, "instanced_draws": 0, "indirect": 0,
            }
            total_actions = [0]
            event_id_max = [0]

            def count(actions):
                for a in actions:
                    total_actions[0] += 1
                    if a.eventId > event_id_max[0]:
                        event_id_max[0] = a.eventId
                    f = a.flags
                    if f & rd.ActionFlags.Drawcall: stats["draw_calls"] += 1
                    if f & rd.ActionFlags.Dispatch: stats["dispatches"] += 1
                    if f & rd.ActionFlags.Clear: stats["clears"] += 1
                    if f & rd.ActionFlags.Copy: stats["copies"] += 1
                    if f & rd.ActionFlags.Resolve: stats["resolves"] += 1
                    if f & rd.ActionFlags.GenMips: stats["gen_mips"] += 1
                    if f & rd.ActionFlags.Present: stats["presents"] += 1
                    if f & (rd.ActionFlags.PushMarker | rd.ActionFlags.SetMarker):
                        stats["markers"] += 1
                    if f & rd.ActionFlags.BeginPass: stats["begin_pass"] += 1
                    if f & rd.ActionFlags.Indexed: stats["indexed_draws"] += 1
                    if f & rd.ActionFlags.Instanced: stats["instanced_draws"] += 1
                    if f & rd.ActionFlags.Indirect: stats["indirect"] += 1
                    if a.children:
                        count(a.children)

            count(roots)

            top_markers = []
            for a in roots:
                if a.flags & rd.ActionFlags.PushMarker:
                    top_markers.append({
                        "name": a.GetName(structured),
                        "event_id": a.eventId,
                        "child_count": Helpers.count_children(a),
                    })

            result["analysis"] = {
                "api": str(api),
                "total_actions": total_actions[0],
                "event_id_range": [0, event_id_max[0]],
                "stats": stats,
                "top_markers": top_markers,
                "texture_count": len(controller.GetTextures()),
                "buffer_count": len(controller.GetBuffers()),
            }

        self._invoke(callback)
        return result["analysis"]

    def get_frame_hierarchy(self, max_depth=3):
        """Marker-only tree (no leaf draws), good for high-level navigation."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"hierarchy": []}

        def callback(controller):
            structured = controller.GetStructuredFile()

            def walk(actions, depth):
                items = []
                if depth >= max_depth:
                    return items
                for a in actions:
                    if not (a.flags & rd.ActionFlags.PushMarker):
                        continue
                    item = {
                        "name": a.GetName(structured),
                        "event_id": a.eventId,
                        "child_count": Helpers.count_children(a),
                    }
                    sub = walk(a.children, depth + 1) if a.children else []
                    if sub:
                        item["markers"] = sub
                    items.append(item)
                return items

            result["hierarchy"] = walk(controller.GetRootActions(), 0)

        self._invoke(callback)
        return result

    def search_actions(self, name_pattern=None, marker_filter=None,
                       event_id_min=None, event_id_max=None, flags=None,
                       limit=200):
        """Flexible action search: by substring, marker scope, eid range, flags."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"matches": [], "count": 0}
        flags_set = set(flags) if flags else None
        needle = (name_pattern or "").lower() if name_pattern else None

        def callback(controller):
            structured = controller.GetStructuredFile()

            def visit(actions, marker_path):
                for a in actions:
                    name = a.GetName(structured)
                    is_push = a.flags & rd.ActionFlags.PushMarker
                    if is_push:
                        marker_path = marker_path + [name]

                    matched = True
                    if needle and needle not in name.lower():
                        matched = False
                    if marker_filter and not any(
                        marker_filter.lower() in m.lower() for m in marker_path
                    ):
                        matched = False
                    if event_id_min is not None and a.eventId < event_id_min:
                        matched = False
                    if event_id_max is not None and a.eventId > event_id_max:
                        matched = False
                    if flags_set:
                        names = Serializers.serialize_flags(a.flags)
                        if not any(f in flags_set for f in names):
                            matched = False

                    if matched and len(result["matches"]) < limit:
                        result["matches"].append({
                            "event_id": a.eventId,
                            "name": name,
                            "flags": Serializers.serialize_flags(a.flags),
                            "marker_path": list(marker_path),
                        })

                    if a.children:
                        visit(a.children, marker_path)

                    if is_push:
                        marker_path = marker_path[:-1]

            visit(controller.GetRootActions(), [])
            result["count"] = len(result["matches"])

        self._invoke(callback)
        return result

    # =================================================================
    # Draw call summaries & stats
    # =================================================================

    def get_drawcall_summary(self, event_id_min=None, event_id_max=None,
                             marker_filter=None, limit=500):
        """Concise per-draw rows (event_id, name, indices, instances, RT, shader)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"draws": [], "count": 0}

        def callback(controller):
            structured = controller.GetStructuredFile()

            def visit(actions, marker_path):
                for a in actions:
                    name = a.GetName(structured)
                    is_push = a.flags & rd.ActionFlags.PushMarker
                    if is_push:
                        marker_path = marker_path + [name]

                    if a.flags & rd.ActionFlags.Drawcall:
                        if event_id_min is not None and a.eventId < event_id_min:
                            pass
                        elif event_id_max is not None and a.eventId > event_id_max:
                            pass
                        elif marker_filter and not any(
                            marker_filter.lower() in m.lower() for m in marker_path
                        ):
                            pass
                        elif len(result["draws"]) < limit:
                            row = {
                                "event_id": a.eventId,
                                "name": name,
                                "num_indices": a.numIndices,
                                "num_instances": a.numInstances,
                                "marker": marker_path[-1] if marker_path else "",
                            }
                            try:
                                controller.SetFrameEvent(a.eventId, False)
                                pipe = controller.GetPipelineState()
                                ps = pipe.GetShader(rd.ShaderStage.Pixel)
                                vs = pipe.GetShader(rd.ShaderStage.Vertex)
                                if ps != rd.ResourceId.Null():
                                    row["pixel_shader"] = str(ps)
                                if vs != rd.ResourceId.Null():
                                    row["vertex_shader"] = str(vs)
                                om = pipe.GetOutputMerger()
                                rts = []
                                if om:
                                    for rt in om.renderTargets:
                                        if rt.resourceId != rd.ResourceId.Null():
                                            rts.append(str(rt.resourceId))
                                row["render_targets"] = rts
                            except Exception:
                                pass
                            result["draws"].append(row)

                    if a.children:
                        visit(a.children, marker_path)

                    if is_push:
                        marker_path = marker_path[:-1]

            visit(controller.GetRootActions(), [])
            result["count"] = len(result["draws"])

        self._invoke(callback)
        return result

    def get_drawcall_stats(self):
        """Aggregate statistics for the entire capture's draw calls."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"stats": None}

        def callback(controller):
            shader_count = {}
            rt_count = {}
            indices_buckets = {"<=100": 0, "<=1000": 0, "<=10000": 0, "<=100000": 0, ">100000": 0}
            instance_buckets = {"1": 0, "2-10": 0, "11-100": 0, "101-1000": 0, ">1000": 0}
            total = [0]
            indexed_total = [0]
            instanced_total = [0]
            indirect_total = [0]

            roots = controller.GetRootActions()

            def visit(actions):
                for a in actions:
                    if a.flags & rd.ActionFlags.Drawcall:
                        total[0] += 1
                        if a.flags & rd.ActionFlags.Indexed:
                            indexed_total[0] += 1
                        if a.flags & rd.ActionFlags.Instanced:
                            instanced_total[0] += 1
                        if a.flags & rd.ActionFlags.Indirect:
                            indirect_total[0] += 1

                        n = a.numIndices
                        if n <= 100: indices_buckets["<=100"] += 1
                        elif n <= 1000: indices_buckets["<=1000"] += 1
                        elif n <= 10000: indices_buckets["<=10000"] += 1
                        elif n <= 100000: indices_buckets["<=100000"] += 1
                        else: indices_buckets[">100000"] += 1

                        ni = a.numInstances
                        if ni <= 1: instance_buckets["1"] += 1
                        elif ni <= 10: instance_buckets["2-10"] += 1
                        elif ni <= 100: instance_buckets["11-100"] += 1
                        elif ni <= 1000: instance_buckets["101-1000"] += 1
                        else: instance_buckets[">1000"] += 1

                        try:
                            controller.SetFrameEvent(a.eventId, False)
                            pipe = controller.GetPipelineState()
                            ps = pipe.GetShader(rd.ShaderStage.Pixel)
                            if ps != rd.ResourceId.Null():
                                key = str(ps)
                                shader_count[key] = shader_count.get(key, 0) + 1
                            om = pipe.GetOutputMerger()
                            if om:
                                for rt in om.renderTargets:
                                    if rt.resourceId != rd.ResourceId.Null():
                                        k = str(rt.resourceId)
                                        rt_count[k] = rt_count.get(k, 0) + 1
                        except Exception:
                            pass

                    if a.children:
                        visit(a.children)

            visit(roots)

            top_shaders = sorted(shader_count.items(), key=lambda kv: -kv[1])[:10]
            top_rts = sorted(rt_count.items(), key=lambda kv: -kv[1])[:10]

            result["stats"] = {
                "total_draws": total[0],
                "indexed_draws": indexed_total[0],
                "instanced_draws": instanced_total[0],
                "indirect_draws": indirect_total[0],
                "indices_buckets": indices_buckets,
                "instance_buckets": instance_buckets,
                "top_pixel_shaders": [{"resource_id": k, "draws": v} for k, v in top_shaders],
                "top_render_targets": [{"resource_id": k, "draws": v} for k, v in top_rts],
                "unique_pixel_shaders": len(shader_count),
                "unique_render_targets": len(rt_count),
            }

        self._invoke(callback)
        return result

    def get_all_passes(self):
        """List every render pass (BeginPass..EndPass or marker-bounded)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"passes": []}

        def callback(controller):
            structured = controller.GetStructuredFile()
            passes = []

            def visit(actions, marker_path):
                for a in actions:
                    is_push = a.flags & rd.ActionFlags.PushMarker
                    if is_push:
                        marker_path = marker_path + [a.GetName(structured)]

                    # Treat top-level pushmarkers as passes if no explicit BeginPass.
                    if a.flags & rd.ActionFlags.BeginPass:
                        passes.append({
                            "name": a.GetName(structured),
                            "event_id": a.eventId,
                            "type": "BeginPass",
                            "marker_path": list(marker_path),
                        })
                    elif is_push and a.children:
                        # Only emit for pushmarkers that contain at least one draw.
                        has_draw = False
                        def has_draw_visit(acts):
                            nonlocal has_draw
                            for x in acts:
                                if x.flags & rd.ActionFlags.Drawcall:
                                    has_draw = True
                                    return
                                if x.children:
                                    has_draw_visit(x.children)
                                    if has_draw:
                                        return
                        has_draw_visit(a.children)
                        if has_draw:
                            passes.append({
                                "name": a.GetName(structured),
                                "event_id": a.eventId,
                                "type": "Marker",
                                "marker_path": list(marker_path),
                            })

                    if a.children:
                        visit(a.children, marker_path)
                    if is_push:
                        marker_path = marker_path[:-1]

            visit(controller.GetRootActions(), [])
            result["passes"] = passes
            result["count"] = len(passes)

        self._invoke(callback)
        return result

    def get_buffer_operations(self, event_id_min=None, event_id_max=None):
        """Copy / Resolve / GenMips / Clear events (non-draw resource ops)."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"operations": []}
        op_flags = (
            rd.ActionFlags.Copy | rd.ActionFlags.Resolve |
            rd.ActionFlags.GenMips | rd.ActionFlags.Clear
        )

        def callback(controller):
            structured = controller.GetStructuredFile()
            ops = []

            def visit(actions):
                for a in actions:
                    if a.flags & op_flags:
                        if event_id_min is not None and a.eventId < event_id_min:
                            pass
                        elif event_id_max is not None and a.eventId > event_id_max:
                            pass
                        else:
                            ops.append({
                                "event_id": a.eventId,
                                "name": a.GetName(structured),
                                "flags": Serializers.serialize_flags(a.flags),
                            })
                    if a.children:
                        visit(a.children)

            visit(controller.GetRootActions())
            result["operations"] = ops
            result["count"] = len(ops)

        self._invoke(callback)
        return result


