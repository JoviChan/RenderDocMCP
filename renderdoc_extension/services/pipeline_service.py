"""
Pipeline state service for RenderDoc.

Covers shader info, full pipeline state dump, comprehensive shader resource
binding listing, and constant-buffer / uniform-buffer value extraction across
D3D11, D3D12, Vulkan and OpenGL/GLES.
"""

import renderdoc as rd

from ..utils import Parsers, Serializers, Helpers, sanitize_sentinel


class PipelineService:
    """Pipeline state service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    # =================================================================
    # Public API
    # =================================================================

    def get_shader_info(self, event_id, stage):
        """Get shader information for a specific stage including cbuffer values."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"shader": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            stage_enum = Parsers.parse_stage(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            entry = pipe.GetShaderEntryPoint(stage_enum)
            reflection = pipe.GetShaderReflection(stage_enum)

            shader_info = {
                "resource_id": str(shader),
                "entry_point": entry,
                "stage": stage,
            }

            # Disassembly
            try:
                targets = controller.GetDisassemblyTargets(True)
                if targets:
                    pipe_obj = Helpers.get_pipeline_object(pipe)
                    disasm = controller.DisassembleShader(pipe_obj, reflection, targets[0])
                    shader_info["disassembly"] = disasm
                    shader_info["disassembly_target"] = str(targets[0])
            except Exception as e:
                shader_info["disassembly_error"] = str(e)

            if Helpers.is_reflection_valid(reflection):
                shader_info["constant_buffers"] = self._get_cbuffer_info(
                    controller, pipe, reflection, stage_enum, shader,
                    expand_depth=2, member_limit=-1,
                )
                shader_info["resources"] = self._get_resource_bindings(reflection)

            result["shader"] = shader_info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["shader"]

    def get_pipeline_state(self, event_id, include_cbuffer_values=True):
        """Get full pipeline state at an event.

        When include_cbuffer_values is True (default), every stage's
        constant buffers carry resolved variable values, not just declarations.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"pipeline": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)

            pipe = controller.GetPipelineState()
            api = controller.GetAPIProperties().pipelineType

            pipeline_info = {
                "event_id": event_id,
                "api": str(api),
            }

            stages = {}
            for stage in Helpers.get_all_shader_stages():
                shader = pipe.GetShader(stage)
                if shader == rd.ResourceId.Null():
                    continue

                stage_info = {
                    "resource_id": str(shader),
                    "entry_point": pipe.GetShaderEntryPoint(stage),
                }
                reflection = pipe.GetShaderReflection(stage)

                stage_info["resources"] = self._get_stage_resources(controller, pipe, stage, reflection)
                stage_info["uavs"] = self._get_stage_uavs(controller, pipe, stage, reflection)
                stage_info["samplers"] = self._get_stage_samplers(pipe, stage, reflection)

                if include_cbuffer_values and Helpers.is_reflection_valid(reflection):
                    stage_info["constant_buffers"] = self._get_cbuffer_info(
                        controller, pipe, reflection, stage, shader,
                        expand_depth=1, member_limit=-1,
                    )
                else:
                    stage_info["constant_buffers"] = self._get_stage_cbuffers_meta(reflection)

                stages[str(stage)] = stage_info

            pipeline_info["shaders"] = stages

            try:
                vp_scissor = pipe.GetViewportScissor()
                if vp_scissor:
                    viewports = []
                    for v in vp_scissor.viewports:
                        viewports.append({
                            "x": v.x, "y": v.y,
                            "width": v.width, "height": v.height,
                            "min_depth": v.minDepth, "max_depth": v.maxDepth,
                        })
                    pipeline_info["viewports"] = viewports
            except Exception:
                pass

            try:
                om = pipe.GetOutputMerger()
                if om:
                    rts = []
                    for i, rt in enumerate(om.renderTargets):
                        if rt.resourceId != rd.ResourceId.Null():
                            rts.append({"index": i, "resource_id": str(rt.resourceId)})
                    pipeline_info["render_targets"] = rts
                    if om.depthTarget.resourceId != rd.ResourceId.Null():
                        pipeline_info["depth_target"] = str(om.depthTarget.resourceId)
            except Exception:
                pass

            try:
                ia = pipe.GetIAState()
                if ia:
                    pipeline_info["input_assembly"] = {"topology": str(ia.topology)}
            except Exception:
                pass

            result["pipeline"] = pipeline_info

        self._invoke(callback)

        if result["error"]:
            raise ValueError(result["error"])
        return result["pipeline"]

    def get_cbuffer_values(self, event_id, stage="pixel", cbuffer_slot=None,
                           expand_depth=2, member_offset=0, member_limit=-1):
        """Read constant-buffer / uniform-buffer values for a draw call.

        Args:
            event_id: Draw call event ID.
            stage: Shader stage (vertex/pixel/compute/...). Default 'pixel'.
            cbuffer_slot: Optional bind slot filter (b0/b3/...). None = all.
            expand_depth: Recursion depth for nested members.
            member_offset: Member-level pagination offset (top-level vars).
            member_limit: Max members per level, -1 = unlimited.

        Works on D3D11/D3D12, Vulkan, OpenGL, OpenGL ES (mobile).
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {
            "success": False,
            "event_id": event_id,
            "stage": stage,
            "shader_id": None,
            "constant_buffers": [],
            "member_offset": member_offset,
            "member_limit": member_limit,
        }

        def callback(controller):
            try:
                controller.SetFrameEvent(event_id, True)
                stage_enum = Helpers.parse_stage_string(stage)

                api_type = controller.GetAPIProperties().pipelineType
                try:
                    result["api"] = api_type.name
                except Exception:
                    result["api"] = str(api_type)

                pipe = controller.GetPipelineState()
                shader = pipe.GetShader(stage_enum)
                reflection = pipe.GetShaderReflection(stage_enum)

                if not Helpers.is_reflection_valid(reflection):
                    result["error"] = "No reflection for %s shader" % stage
                    return

                result["shader_id"] = str(shader)

                cbs = self._get_cbuffer_info(
                    controller, pipe, reflection, stage_enum, shader,
                    expand_depth=expand_depth,
                    member_limit=member_limit,
                    cbuffer_slot=cbuffer_slot,
                    member_offset=member_offset,
                )
                result["constant_buffers"] = cbs
                result["success"] = True
            except Exception as e:
                import traceback
                result["error"] = str(e)
                result["traceback"] = traceback.format_exc()

        self._invoke(callback)
        return result

    def expand_cbuffer_member(self, event_id, cbuffer_slot, member_path,
                              stage="pixel", expand_depth=2, member_limit=-1):
        """Drill into a deep cbuffer member by dotted/index path.

        Path examples: ``_child0[10]``, ``matrix.row0[2]``,
        ``LocalFogPackedParams.x``.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {
            "success": False,
            "event_id": event_id,
            "cbuffer_slot": cbuffer_slot,
            "path": member_path,
            "stage": stage,
        }

        def callback(controller):
            try:
                controller.SetFrameEvent(event_id, True)
                stage_enum = Helpers.parse_stage_string(stage)

                pipe = controller.GetPipelineState()
                shader = pipe.GetShader(stage_enum)
                reflection = pipe.GetShaderReflection(stage_enum)
                if not Helpers.is_reflection_valid(reflection):
                    result["error"] = "No reflection for %s shader" % stage
                    return

                api_type = controller.GetAPIProperties().pipelineType
                is_opengl = (api_type == rd.GraphicsAPI.OpenGL)

                cb_block, cb_idx = self._find_cb_block(reflection, cbuffer_slot)
                if cb_block is None:
                    result["error"] = "Cbuffer slot b%d not found" % cbuffer_slot
                    return

                slot = self._slot_of_block(cb_block, cb_idx)
                res_id, byte_off, byte_sz = self._resolve_cb_binding(
                    controller, pipe, stage_enum, slot, cb_idx, is_opengl, cb_block,
                )

                vars_list = self._fetch_cbuffer_variables(
                    controller, pipe, shader, reflection, stage_enum, slot, cb_idx,
                    res_id, byte_off, byte_sz, is_opengl,
                )
                vars_list = list(vars_list or [])
                if (is_opengl
                        and len(vars_list) == 1
                        and len(getattr(vars_list[0], "members", []) or []) > 0):
                    vars_list = list(vars_list[0].members)

                target = Serializers.find_member_by_path(vars_list, member_path)
                if target is None:
                    result["error"] = "Path '%s' not found in cbuffer b%d" % (
                        member_path, cbuffer_slot,
                    )
                    return

                dumped = Serializers.shader_var_to_dict(
                    target, expand_depth=expand_depth, member_limit=member_limit,
                )
                result.update(dumped)
                result["success"] = True
            except Exception as e:
                import traceback
                result["error"] = str(e)
                result["traceback"] = traceback.format_exc()

        self._invoke(callback)
        return result

    def get_shader_resources(self, event_id, stage):
        """One-shot dump of every binding for a given shader stage.

        Returns SRVs, UAVs, samplers, and constant buffers (with resolved
        values) — equivalent to the RenderDoc Pipeline State viewer for
        that stage.
        """
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"stage": stage, "data": None, "error": None}

        def callback(controller):
            controller.SetFrameEvent(event_id, True)
            pipe = controller.GetPipelineState()
            stage_enum = Helpers.parse_stage_string(stage)

            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                result["error"] = "No %s shader bound" % stage
                return

            reflection = pipe.GetShaderReflection(stage_enum)

            data = {
                "event_id": event_id,
                "stage": stage,
                "shader_id": str(shader),
                "entry_point": pipe.GetShaderEntryPoint(stage_enum),
            }

            data["resources"] = self._get_stage_resources(controller, pipe, stage_enum, reflection)
            data["uavs"] = self._get_stage_uavs(controller, pipe, stage_enum, reflection)
            data["samplers"] = self._get_stage_samplers(pipe, stage_enum, reflection)

            if Helpers.is_reflection_valid(reflection):
                data["constant_buffers"] = self._get_cbuffer_info(
                    controller, pipe, reflection, stage_enum, shader,
                    expand_depth=2, member_limit=-1,
                )

            result["data"] = data

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["data"]

    def list_disassembly_targets(self):
        """Available disassembly targets (e.g. 'DXBC','HLSL','GLSL','SPIR-V')."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        out = {"targets": []}

        def cb(controller):
            try:
                out["targets"] = [str(t) for t in controller.GetDisassemblyTargets(True)]
            except Exception as e:
                out["error"] = str(e)

        self._invoke(cb)
        return out

    def disassemble_shader(self, event_id, stage, target=None):
        """Get raw disassembly text. ``target`` selects DXBC/SPIR-V/etc."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        out = {"event_id": event_id, "stage": stage}

        def cb(controller):
            controller.SetFrameEvent(event_id, True)
            pipe = controller.GetPipelineState()
            stage_enum = Helpers.parse_stage_string(stage)
            shader = pipe.GetShader(stage_enum)
            if shader == rd.ResourceId.Null():
                out["error"] = "No %s shader bound" % stage
                return
            reflection = pipe.GetShaderReflection(stage_enum)
            try:
                targets = list(controller.GetDisassemblyTargets(True))
                chosen = targets[0]
                if target:
                    for t in targets:
                        if str(t).lower() == target.lower():
                            chosen = t
                            break
                pipe_obj = Helpers.get_pipeline_object(pipe)
                out["target"] = str(chosen)
                out["disassembly"] = controller.DisassembleShader(
                    pipe_obj, reflection, chosen
                )
                out["available_targets"] = [str(t) for t in targets]
            except Exception as e:
                out["error"] = str(e)

        self._invoke(cb)
        return out

    def decompile_shader(self, event_id, stage, language="hlsl"):
        """Decompile to HLSL / GLSL by selecting matching disassembly target."""
        out = self.disassemble_shader(event_id, stage, target=language)
        out["language"] = language
        if "disassembly" in out:
            out["source"] = out.pop("disassembly")
        return out

    # =================================================================
    # Pixel History
    # =================================================================

    def get_pixel_history(self, resource_id, x, y, sub_resource=None):
        """Get the modification history of a single pixel."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"pixel_history": None, "error": None}

        def callback(controller):
            try:
                rid = Parsers.parse_resource_id(resource_id)

                tex_desc = None
                for tex in controller.GetTextures():
                    if tex.resourceId == rid:
                        tex_desc = tex
                        break
                if tex_desc is None:
                    result["error"] = "Texture not found: %s" % resource_id
                    return

                sub = sub_resource if sub_resource is not None else rd.Subresource()
                comp_type = rd.CompType.Float

                history = controller.PixelHistory(rid, x, y, sub, comp_type)

                entries = []
                for h in history:
                    entry = {
                        "event_id": h.eventId,
                        "passed": not h.Passed() if hasattr(h, "Passed") else None,
                    }
                    try:
                        entry["primitive_id"] = h.primitiveID
                    except Exception:
                        pass

                    def _pixel_val(pv):
                        try:
                            return [pv.floatValue[i] for i in range(4)]
                        except Exception:
                            try:
                                return [pv.uintValue[i] for i in range(4)]
                            except Exception:
                                return None

                    try:
                        entry["pre_mod"] = _pixel_val(h.preMod)
                        entry["post_mod"] = _pixel_val(h.postMod)
                        entry["shader_out"] = _pixel_val(h.shaderOut)
                    except Exception:
                        pass

                    try:
                        entry["depth_failed"] = h.depthTestFailed
                        entry["stencil_failed"] = h.stencilTestFailed
                        entry["backface_culled"] = h.backfaceCulled
                        entry["scissor_clipped"] = h.scissorClipped
                        entry["shader_discarded"] = h.shaderDiscarded
                    except Exception:
                        pass

                    entries.append(entry)

                result["pixel_history"] = {
                    "resource_id": resource_id,
                    "x": x, "y": y,
                    "texture_width": tex_desc.width,
                    "texture_height": tex_desc.height,
                    "format": str(tex_desc.format.Name()),
                    "modifications": entries,
                    "count": len(entries),
                }
            except Exception as e:
                import traceback
                result["error"] = str(e) + "\n" + traceback.format_exc()

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["pixel_history"]

    # =================================================================
    # Shader Debug (stateful — traces stored per session)
    # =================================================================

    _debug_sessions = {}
    _next_session_id = [1]

    def debug_pixel_shader(self, event_id, x, y, sample=0, primitive=None):
        """Start a pixel shader debug session at (x,y). Returns session_id."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"session": None, "error": None}

        def callback(controller):
            try:
                controller.SetFrameEvent(event_id, True)

                input_spec = rd.DebugPixelInputs()
                input_spec.sample = sample
                if primitive is not None:
                    input_spec.primitive = primitive

                trace = controller.DebugPixel(x, y, input_spec)
                if trace is None:
                    result["error"] = "Debug failed — no shader at (%d,%d)" % (x, y)
                    return

                sid = "dbg_%d" % PipelineService._next_session_id[0]
                PipelineService._next_session_id[0] += 1
                PipelineService._debug_sessions[sid] = {
                    "trace": trace,
                    "event_id": event_id,
                    "x": x, "y": y,
                }

                result["session"] = {
                    "session_id": sid,
                    "event_id": event_id,
                    "x": x, "y": y,
                    "num_instructions": len(trace.instInfo) if hasattr(trace, "instInfo") else None,
                }
            except Exception as e:
                import traceback
                result["error"] = str(e) + "\n" + traceback.format_exc()

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["session"]

    def step_shader_debugger(self, session_id, step_count=1):
        """Step the debug session forward. Returns variable state after step."""
        if session_id not in PipelineService._debug_sessions:
            raise ValueError("Unknown session: %s" % session_id)

        result = {"state": None, "error": None}
        session = PipelineService._debug_sessions[session_id]

        def callback(controller):
            try:
                trace = session["trace"]
                states = controller.ContinueDebug(trace)
                if not states:
                    result["state"] = {"finished": True}
                    return

                last = states[-1] if states else None
                if last is None:
                    result["state"] = {"finished": True}
                    return

                variables = []
                for v in (last.changes if hasattr(last, "changes") else []):
                    variables.append(Serializers.shader_var_to_dict(v))

                result["state"] = {
                    "session_id": session_id,
                    "step_index": getattr(last, "stepIndex", None),
                    "finished": bool(getattr(last, "flags", 0) & 1) if hasattr(last, "flags") else False,
                    "changed_variables": variables,
                }
            except Exception as e:
                import traceback
                result["error"] = str(e) + "\n" + traceback.format_exc()

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["state"]

    def get_shader_state(self, session_id):
        """Get current variable state of a debug session."""
        if session_id not in PipelineService._debug_sessions:
            raise ValueError("Unknown session: %s" % session_id)

        result = {"state": None, "error": None}
        session = PipelineService._debug_sessions[session_id]

        def callback(controller):
            try:
                trace = session["trace"]
                state = controller.GetDebugState(trace) if hasattr(controller, "GetDebugState") else None
                if state is None:
                    result["state"] = {"session_id": session_id, "variables": []}
                    return

                variables = []
                for v in (getattr(state, "variables", []) or []):
                    variables.append(Serializers.shader_var_to_dict(v))

                result["state"] = {
                    "session_id": session_id,
                    "variables": variables,
                }
            except Exception as e:
                import traceback
                result["error"] = str(e) + "\n" + traceback.format_exc()

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result["state"]

    def free_shader_debugger(self, session_id):
        """Free a debug session."""
        if session_id not in PipelineService._debug_sessions:
            raise ValueError("Unknown session: %s" % session_id)

        session = PipelineService._debug_sessions.pop(session_id)

        def callback(controller):
            try:
                trace = session.get("trace")
                if trace and hasattr(controller, "FreeTrace"):
                    controller.FreeTrace(trace)
            except Exception:
                pass

        self._invoke(callback)
        return {"freed": True, "session_id": session_id}

    # =================================================================
    # Shader Edit
    # =================================================================

    _shader_edits = {}

    def apply_shader_edit(self, event_id, stage, source_code, language="hlsl"):
        """Build a custom shader from source and apply it to a draw call."""
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")

        result = {"applied": False, "error": None}

        def callback(controller):
            try:
                controller.SetFrameEvent(event_id, True)
                stage_enum = Helpers.parse_stage_string(stage)
                pipe = controller.GetPipelineState()
                orig_shader = pipe.GetShader(stage_enum)
                reflection = pipe.GetShaderReflection(stage_enum)
                entry = pipe.GetShaderEntryPoint(stage_enum)
                pipe_obj = Helpers.get_pipeline_object(pipe)

                enc = rd.ShaderEncoding.HLSL if language.lower() == "hlsl" else rd.ShaderEncoding.GLSL

                built = controller.BuildCustomShader(
                    entry, source_code, enc, rd.ShaderCompileFlags(), stage_enum
                )

                if built.resourceId == rd.ResourceId.Null():
                    errors = getattr(built, "errors", "Unknown error")
                    result["error"] = "Shader compile failed: %s" % str(errors)
                    return

                edits = controller.GetCustomShaderReplacements()
                edits.append(rd.ShaderReplacement(orig_shader, built.resourceId))
                controller.SetCustomShaderReplacements(edits)

                key = "%d_%s" % (event_id, stage)
                PipelineService._shader_edits[key] = {
                    "original": orig_shader,
                    "replacement": built.resourceId,
                    "event_id": event_id,
                    "stage": stage,
                }

                result["applied"] = True
                result["edit_key"] = key
                result["custom_shader_id"] = str(built.resourceId)
            except Exception as e:
                import traceback
                result["error"] = str(e) + "\n" + traceback.format_exc()

        self._invoke(callback)
        if result["error"]:
            raise ValueError(result["error"])
        return result

    def remove_shader_edit(self, event_id, stage):
        """Remove a previously applied shader edit."""
        key = "%d_%s" % (event_id, stage)
        edit = PipelineService._shader_edits.pop(key, None)
        if edit is None:
            raise ValueError("No active edit for event %d stage %s" % (event_id, stage))

        def callback(controller):
            try:
                edits = controller.GetCustomShaderReplacements()
                new_edits = [e for e in edits if e.original != edit["original"]]
                controller.SetCustomShaderReplacements(new_edits)
                controller.FreeCustomShader(edit["replacement"])
            except Exception:
                pass

        self._invoke(callback)
        return {"removed": True, "edit_key": key}

    # =================================================================
    # Internal: stage binding extractors (SRV/UAV/Sampler)
    # =================================================================

    def _get_stage_resources(self, controller, pipe, stage, reflection):
        """Get shader resource views (SRVs) for a stage"""
        resources = []
        try:
            srvs = pipe.GetReadOnlyResources(stage, False)

            name_map = {}
            if reflection:
                for res in reflection.readOnlyResources:
                    name_map[res.fixedBindNumber] = res.name

            for srv in srvs:
                if srv.descriptor.resource == rd.ResourceId.Null():
                    continue

                slot = srv.access.index
                res_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                    "resource_id": str(srv.descriptor.resource),
                }

                res_info.update(
                    self._get_resource_details(controller, srv.descriptor.resource)
                )

                res_info["first_mip"] = srv.descriptor.firstMip
                res_info["num_mips"] = srv.descriptor.numMips
                res_info["first_slice"] = srv.descriptor.firstSlice
                res_info["num_slices"] = srv.descriptor.numSlices

                resources.append(res_info)
        except Exception as e:
            resources.append({"error": str(e)})

        return resources

    def _get_stage_uavs(self, controller, pipe, stage, reflection):
        """Get unordered access views (UAVs) for a stage"""
        uavs = []
        try:
            uav_list = pipe.GetReadWriteResources(stage, False)

            name_map = {}
            if reflection:
                for res in reflection.readWriteResources:
                    name_map[res.fixedBindNumber] = res.name

            for uav in uav_list:
                if uav.descriptor.resource == rd.ResourceId.Null():
                    continue

                slot = uav.access.index
                uav_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                    "resource_id": str(uav.descriptor.resource),
                }

                uav_info.update(
                    self._get_resource_details(controller, uav.descriptor.resource)
                )

                uav_info["first_element"] = uav.descriptor.firstMip
                uav_info["num_elements"] = uav.descriptor.numMips

                uavs.append(uav_info)
        except Exception as e:
            uavs.append({"error": str(e)})

        return uavs

    def _get_stage_samplers(self, pipe, stage, reflection):
        """Get samplers for a stage"""
        samplers = []
        try:
            sampler_list = pipe.GetSamplers(stage, False)

            name_map = {}
            if reflection:
                for samp in reflection.samplers:
                    name_map[samp.fixedBindNumber] = samp.name

            for samp in sampler_list:
                slot = samp.access.index
                samp_info = {
                    "slot": slot,
                    "name": name_map.get(slot, ""),
                }

                desc = samp.descriptor
                try:
                    samp_info["address_u"] = str(desc.addressU)
                    samp_info["address_v"] = str(desc.addressV)
                    samp_info["address_w"] = str(desc.addressW)
                except AttributeError:
                    pass

                try:
                    samp_info["filter"] = str(desc.filter)
                except AttributeError:
                    pass

                try:
                    samp_info["max_anisotropy"] = desc.maxAnisotropy
                except AttributeError:
                    pass

                try:
                    samp_info["min_lod"] = desc.minLOD
                    samp_info["max_lod"] = desc.maxLOD
                    samp_info["mip_lod_bias"] = desc.mipLODBias
                except AttributeError:
                    pass

                try:
                    samp_info["border_color"] = [
                        desc.borderColor[0], desc.borderColor[1],
                        desc.borderColor[2], desc.borderColor[3],
                    ]
                except (AttributeError, TypeError):
                    pass

                try:
                    samp_info["compare_function"] = str(desc.compareFunction)
                except AttributeError:
                    pass

                samplers.append(samp_info)
        except Exception as e:
            samplers.append({"error": str(e)})

        return samplers

    def _get_stage_cbuffers_meta(self, reflection):
        """Lightweight cbuffer descriptors only (no values)."""
        cbuffers = []
        try:
            if not reflection:
                return cbuffers

            for cb_idx, cb in enumerate(reflection.constantBlocks):
                slot = self._slot_of_block(cb, cb_idx)
                cb_info = {
                    "slot": slot,
                    "name": cb.name,
                    "byte_size": sanitize_sentinel(getattr(cb, "byteSize", 0)),
                    "variable_count": len(cb.variables) if cb.variables else 0,
                }
                cbuffers.append(cb_info)
        except Exception as e:
            cbuffers.append({"error": str(e)})

        return cbuffers

    # =================================================================
    # Internal: cbuffer value extraction (D3D / Vulkan / GL)
    # =================================================================

    def _slot_of_block(self, cb_block, cb_idx):
        """Read the real bind slot from a ConstantBlock, falling back to index."""
        return getattr(
            cb_block, "fixedBindNumber",
            getattr(cb_block, "bindPoint", cb_idx),
        )

    def _find_cb_block(self, reflection, cbuffer_slot):
        """Find the ConstantBlock matching cbuffer_slot. Returns (block, idx)."""
        for cb_idx, cb in enumerate(reflection.constantBlocks):
            slot = self._slot_of_block(cb, cb_idx)
            if cbuffer_slot is None or slot == cbuffer_slot:
                return cb, cb_idx
        return None, -1

    def _resolve_cb_binding(self, controller, pipe, stage, slot, cb_idx, is_opengl, cb_block):
        """Locate the bound buffer (resource_id, byte_offset, byte_size) for a CB.

        Handles three API families:
        * D3D11/12, Vulkan -> GetConstantBlock(stage, slot, 0)
        * OpenGL/GLES      -> GetDescriptorAccess + GetDescriptors
        """
        default_size = sanitize_sentinel(getattr(cb_block, "byteSize", 0)) or 0
        res_id = rd.ResourceId.Null()
        byte_off = 0
        byte_sz = default_size

        if is_opengl:
            try:
                gl_state = controller.GetGLPipelineState()
                accesses = controller.GetDescriptorAccess()
                desc_store = getattr(gl_state, "descriptorStore", rd.ResourceId.Null())
                for acc in accesses:
                    try:
                        if (int(getattr(acc, "type", -1)) == 1  # ConstantBuffer
                                and int(getattr(acc, "stage", -1)) == int(stage)
                                and int(getattr(acc, "index", -1)) == cb_idx):
                            dr = rd.DescriptorRange()
                            dr.offset = acc.byteOffset
                            dr.count = 1
                            descs = controller.GetDescriptors(desc_store, [dr])
                            if descs:
                                d = descs[0]
                                res_id = getattr(d, "resource", rd.ResourceId.Null())
                                byte_off = getattr(d, "byteOffset", 0)
                                raw_sz = sanitize_sentinel(getattr(d, "byteSize", 0))
                                if raw_sz is not None:
                                    byte_sz = raw_sz
                            break
                    except Exception:
                        continue
            except Exception:
                pass
            return res_id, byte_off, byte_sz

        # D3D11 / D3D12 / Vulkan
        try:
            used_desc = pipe.GetConstantBlock(stage, slot, 0)
            desc_info = getattr(used_desc, "descriptor", None)
            if desc_info is not None:
                res_id = getattr(desc_info, "resource", res_id) or res_id
                byte_off = getattr(desc_info, "byteOffset", 0)
                raw_sz = sanitize_sentinel(getattr(desc_info, "byteSize", 0))
                if raw_sz is not None:
                    byte_sz = raw_sz
        except Exception:
            try:
                all_cbs = pipe.GetConstantBlocks(stage, True)
                for ud in all_cbs:
                    acc = getattr(ud, "access", None)
                    if acc and int(getattr(acc, "index", -1)) == slot:
                        desc_info = getattr(ud, "descriptor", None)
                        if desc_info:
                            res_id = getattr(desc_info, "resource", res_id) or res_id
                            byte_off = getattr(desc_info, "byteOffset", 0)
                            raw_sz = sanitize_sentinel(getattr(desc_info, "byteSize", 0))
                            if raw_sz is not None:
                                byte_sz = raw_sz
                        break
            except Exception:
                pass

        return res_id, byte_off, byte_sz

    def _fetch_cbuffer_variables(self, controller, pipe, shader, reflection,
                                  stage, slot, cb_idx, res_id, byte_off, byte_sz,
                                  is_opengl):
        """Call GetCBufferVariableContents with the right signature for the API."""
        if res_id is None:
            res_id = rd.ResourceId.Null()
        ep = pipe.GetShaderEntryPoint(stage)
        ep_str = ep if isinstance(ep, str) else getattr(ep, "name", str(ep))
        pipe_obj = Helpers.get_pipeline_object(pipe)

        if is_opengl:
            gl_state = controller.GetGLPipelineState()
            gl_attr_map = {
                rd.ShaderStage.Vertex: "vertexShader",
                rd.ShaderStage.Fragment: "fragmentShader",
                rd.ShaderStage.Pixel: "fragmentShader",
                rd.ShaderStage.Geometry: "geometryShader",
                rd.ShaderStage.Hull: "tessControlShader",
                rd.ShaderStage.Domain: "tessEvalShader",
                rd.ShaderStage.Compute: "computeShader",
            }
            attr = gl_attr_map.get(stage, "vertexShader")
            gl_ss = getattr(gl_state, attr, None)
            prog_id = (getattr(gl_ss, "programResourceId", rd.ResourceId.Null())
                       if gl_ss else rd.ResourceId.Null())
            shader_id2 = (getattr(gl_ss, "shaderResourceId", rd.ResourceId.Null())
                          if gl_ss else rd.ResourceId.Null())
            # GLES uses the enumerated UBO block index, not fixedBindNumber.
            return controller.GetCBufferVariableContents(
                prog_id, shader_id2, stage, ep_str,
                cb_idx, res_id, byte_off, byte_sz,
            )

        # D3D / Vulkan: 8-arg signature, with 7-arg fallback.
        try:
            return controller.GetCBufferVariableContents(
                pipe_obj, shader, stage, ep_str, slot, res_id, byte_off, byte_sz,
            )
        except TypeError:
            return controller.GetCBufferVariableContents(
                shader, stage, ep_str, slot, res_id, byte_off, byte_sz,
            )

    def _get_cbuffer_info(self, controller, pipe, reflection, stage, shader,
                          expand_depth=2, member_limit=-1, cbuffer_slot=None,
                          member_offset=0):
        """Comprehensive constant-buffer dump for a shader stage.

        Resolves bound resource ID, range, then calls GetCBufferVariableContents
        with the API-appropriate signature. Returns one entry per CB block
        (filtered by cbuffer_slot if provided), each carrying resolved
        ``variables`` (recursively serialized) plus pagination info.
        """
        cbuffers = []
        if not Helpers.is_reflection_valid(reflection):
            return cbuffers

        api_type = controller.GetAPIProperties().pipelineType
        is_opengl = (api_type == rd.GraphicsAPI.OpenGL)

        for cb_idx, cb_block in enumerate(reflection.constantBlocks):
            slot = self._slot_of_block(cb_block, cb_idx)
            if cbuffer_slot is not None and slot != cbuffer_slot:
                continue

            cb_entry = {
                "slot": slot,
                "name": cb_block.name,
                "byte_size": sanitize_sentinel(getattr(cb_block, "byteSize", 0)),
                "variable_count": len(cb_block.variables) if cb_block.variables else 0,
                "bound_resource": None,
                "bound_name": None,
                "variables": [],
            }

            # 1) Resolve the actual bound buffer + range.
            try:
                res_id, byte_off, byte_sz = self._resolve_cb_binding(
                    controller, pipe, stage, slot, cb_idx, is_opengl, cb_block,
                )
                if res_id and str(res_id) not in ("ResourceId::0", "None", ""):
                    cb_entry["bound_resource"] = str(res_id)
                    cb_entry["bound_name"] = Helpers.get_resource_name(self.ctx, res_id)
                cb_entry["byte_offset"] = byte_off
                cb_entry["byte_range"] = byte_sz
            except Exception as e:
                cb_entry["bind_error"] = str(e)
                res_id, byte_off, byte_sz = rd.ResourceId.Null(), 0, cb_entry["byte_size"] or 0

            # 2) Pull the resolved variable values.
            try:
                vars_list = self._fetch_cbuffer_variables(
                    controller, pipe, shader, reflection, stage, slot, cb_idx,
                    res_id, byte_off, byte_sz, is_opengl,
                )
                vars_list = list(vars_list or [])

                # GLES often returns a single root struct holding all members;
                # unwrap so callers see top-level uniforms.
                if (is_opengl
                        and len(vars_list) == 1
                        and len(getattr(vars_list[0], "members", []) or []) > 0):
                    vars_list = list(vars_list[0].members)

                total_members = len(vars_list)
                if member_limit == -1:
                    page = vars_list[member_offset:]
                else:
                    page = vars_list[member_offset:member_offset + member_limit]

                cb_entry["variables"] = Serializers.serialize_variables(
                    page, expand_depth=expand_depth, member_limit=member_limit,
                )
                cb_entry["total_members"] = total_members
                cb_entry["member_offset"] = member_offset
                cb_entry["member_limit"] = member_limit
                if member_limit == -1:
                    cb_entry["has_more_members"] = False
                else:
                    cb_entry["has_more_members"] = (
                        member_offset + member_limit < total_members
                    )
            except Exception as e:
                cb_entry["data_error"] = str(e)

            cbuffers.append(cb_entry)

        return cbuffers

    # =================================================================
    # Internal: misc
    # =================================================================

    def _get_resource_details(self, controller, resource_id):
        """Get details about a resource (texture or buffer)"""
        details = {}

        try:
            resource_name = self.ctx.GetResourceName(resource_id)
            if resource_name:
                details["resource_name"] = resource_name
        except Exception:
            pass

        for tex in controller.GetTextures():
            if tex.resourceId == resource_id:
                details["type"] = "texture"
                details["width"] = tex.width
                details["height"] = tex.height
                details["depth"] = tex.depth
                details["array_size"] = tex.arraysize
                details["mip_levels"] = tex.mips
                details["format"] = str(tex.format.Name())
                details["dimension"] = str(tex.type)
                details["msaa_samples"] = tex.msSamp
                return details

        for buf in controller.GetBuffers():
            if buf.resourceId == resource_id:
                details["type"] = "buffer"
                details["length"] = buf.length
                return details

        return details

    def _get_resource_bindings(self, reflection):
        """Get shader resource bindings from reflection"""
        resources = []

        try:
            for res in reflection.readOnlyResources:
                resources.append({
                    "name": res.name,
                    "type": str(res.resType),
                    "binding": res.fixedBindNumber,
                    "access": "ReadOnly",
                })
        except Exception:
            pass

        try:
            for res in reflection.readWriteResources:
                resources.append({
                    "name": res.name,
                    "type": str(res.resType),
                    "binding": res.fixedBindNumber,
                    "access": "ReadWrite",
                })
        except Exception:
            pass

        return resources
