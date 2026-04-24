extends Node3D

@onready var animation_player = $AnimationPlayer
@onready var camera = $Camera3D

# Runtime camera tracking state
var _cam_track: Array    = []

var _cam_seg_idx: int    = 0
var _seg_start_t: float  = 0.0
var _orbit_angle: float  = 0.0
var _asset_manifest: Dictionary = {}  # actor_id → {path, target_size} | null
var _attach_map: Dictionary = {}      # child_id → parent_id (for attached actors)

func _ready():
	print("DirectorEngine initialized.")
	var sequence = _load_sequence("res://director_sequence.json")
	if sequence.is_empty():
		print("No valid director sequence found.")
		return

	_asset_manifest = sequence.get("asset_manifest", {})
	_setup_scene(sequence.get("scene_setup", {}))
	_spawn_actors(sequence)
	_build_animation(sequence)
	_cam_track = sequence.get("camera_track", [])
	animation_player.animation_finished.connect(_on_animation_finished)
	print("Action!")
	animation_player.play("director_cut")

func _process(delta: float) -> void:
	if not animation_player.is_playing():
		return
	var t = animation_player.current_animation_position
	_update_camera(t, delta)

# ── Helpers ────────────────────────────────────────────────────────────────────

func _v3(d: Dictionary, dx: float = 0.0, dy: float = 1.0, dz: float = 5.0) -> Vector3:
	return Vector3(float(d.get("x", dx)), float(d.get("y", dy)), float(d.get("z", dz)))

func _actor_pos(id: String, fallback: Vector3 = Vector3.ZERO) -> Vector3:
	if id == "" or not has_node(NodePath(id)):
		return fallback
	return get_node(NodePath(id)).global_position

func _actors_centroid() -> Vector3:
	var sum   = Vector3.ZERO
	var count = 0
	for child in get_children():
		if child is Node3D and child.name not in ["WorldEnvironment", "Sun", "Ground"]:
			sum   += child.global_position
			count += 1
	return sum / max(count, 1)

# ── Runtime Camera Controller ─────────────────────────────────────────────────

func _update_camera(t: float, delta: float) -> void:
	if _cam_track.is_empty():
		return

	# Advance segment index
	while _cam_seg_idx + 1 < _cam_track.size() and \
		  float(_cam_track[_cam_seg_idx + 1].get("time", 0)) <= t:
		_cam_seg_idx += 1
		_seg_start_t  = float(_cam_track[_cam_seg_idx].get("time", 0))
		var tr = str(_cam_track[_cam_seg_idx].get("transition", "smooth"))
		if tr == "cut":
			_orbit_angle = 0.0  # reset orbit on hard cut

	var seg  = _cam_track[_cam_seg_idx]
	var mode = str(seg.get("mode", "follow"))
	camera.fov = float(seg.get("fov", 65))

	var target_id  = str(seg.get("target_id",  ""))
	var look_at_id = str(seg.get("look_at_id", target_id))
	var smooth     = str(seg.get("transition", "smooth")) == "smooth"
	var w          = 0.12 if smooth else 1.0  # lerp weight per frame at 60fps

	match mode:
		"follow":
			var offset  = _v3(seg.get("offset", {"x":0,"y":2,"z":7}), 0, 2, 7)
			var tpos    = _actor_pos(target_id, camera.global_position)
			var desired = tpos + offset
			camera.global_position = camera.global_position.lerp(desired, w)
			var look_p = _actor_pos(look_at_id, tpos) + Vector3(0, 0.9, 0)
			camera.look_at(look_p)

		"orbit":
			var tpos   = _actor_pos(target_id, Vector3.ZERO)
			var radius = float(seg.get("radius", 7.0))
			var height = float(seg.get("height", 3.0))
			var speed  = float(seg.get("orbit_speed", 0.6))
			_orbit_angle += speed * delta
			var desired = tpos + Vector3(cos(_orbit_angle) * radius, height, sin(_orbit_angle) * radius)
			camera.global_position = camera.global_position.lerp(desired, w)
			camera.look_at(tpos + Vector3(0, 0.9, 0))

		"static_look":
			var desired = _v3(seg.get("position", {"x":8,"y":2,"z":0}), 8, 2, 0)
			camera.global_position = camera.global_position.lerp(desired, w * 0.4)
			var look_p = _actor_pos(look_at_id, _actors_centroid()) + Vector3(0, 0.9, 0)
			camera.look_at(look_p)

		"wide_look":
			var desired = _v3(seg.get("position", {"x":0,"y":12,"z":10}), 0, 12, 10)
			camera.global_position = camera.global_position.lerp(desired, w * 0.3)
			camera.look_at(_actors_centroid() + Vector3(0, 0.5, 0))

		"free":
			# Legacy absolute-position keyframe — handled by AnimationPlayer if track exists
			pass

func _load_sequence(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file = FileAccess.open(path, FileAccess.READ)
	var content = file.get_as_text()
	var json = JSON.new()
	if json.parse(content) == OK:
		return json.data
	return {}

# ──────────────────────────────────────────────
# Scene setup (sky / sun / fog / ground / props)
# ──────────────────────────────────────────────

func _setup_scene(s: Dictionary) -> void:
	_setup_sky_and_env(s)
	_setup_sun(s.get("sun", {}))
	var ground_d = s.get("ground", {})
	if ground_d.get("enabled", true):
		_spawn_ground(ground_d)
	for prop_d in s.get("props", []):
		_spawn_prop(prop_d)

func _c(d: Dictionary, r: float = 0.5, g: float = 0.5, b: float = 0.5) -> Color:
	return Color(float(d.get("r", r)), float(d.get("g", g)), float(d.get("b", b)))

func _setup_sky_and_env(s: Dictionary) -> void:
	var world_env  = WorldEnvironment.new()
	var env        = Environment.new()
	var sky        = Sky.new()
	var sky_mat    = ProceduralSkyMaterial.new()

	var sky_d = s.get("sky", {})
	sky_mat.sky_top_color     = _c(sky_d.get("top_color",     {"r":0.18,"g":0.36,"b":0.72}), 0.18, 0.36, 0.72)
	sky_mat.sky_horizon_color = _c(sky_d.get("horizon_color", {"r":0.6, "g":0.72,"b":0.88}), 0.6,  0.72, 0.88)
	sky_mat.ground_bottom_color = Color(0.18, 0.16, 0.14)
	sky.sky_material  = sky_mat
	env.sky           = sky
	env.background_mode = Environment.BG_SKY

	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = float(s.get("ambient_energy", 0.5))

	var fog_d = s.get("fog", {})
	env.fog_enabled = bool(fog_d.get("enabled", false))
	if env.fog_enabled:
		env.fog_light_color = _c(fog_d.get("color", {"r":0.8,"g":0.8,"b":0.8}), 0.8, 0.8, 0.8)
		env.fog_density     = float(fog_d.get("density", 0.01))

	world_env.environment = env
	world_env.name = "WorldEnvironment"
	add_child(world_env)

func _setup_sun(sun_d: Dictionary) -> void:
	if not sun_d.get("enabled", true):
		return
	var light = DirectionalLight3D.new()
	var ed    = sun_d.get("euler_degrees", {"x": -55.0, "y": -30.0, "z": 0.0})
	light.rotation_degrees = Vector3(float(ed.get("x",-55)), float(ed.get("y",-30)), float(ed.get("z",0)))
	light.light_color      = _c(sun_d.get("color", {"r":1.0,"g":0.95,"b":0.8}), 1.0, 0.95, 0.8)
	light.light_energy     = float(sun_d.get("energy", 1.5))
	light.shadow_enabled   = true
	light.name = "Sun"
	add_child(light)

func _spawn_ground(ground_d: Dictionary) -> void:
	var size = float(ground_d.get("size", 60.0))

	# StaticBody3D so RigidBody physics actors land on it
	var sb  = StaticBody3D.new()
	var pm_mat = StandardMaterial3D.new()
	pm_mat.albedo_color = _c(ground_d.get("color", {"r":0.28,"g":0.32,"b":0.22}), 0.28, 0.32, 0.22)
	pm_mat.roughness    = 0.9

	var mi = MeshInstance3D.new()
	var pm = PlaneMesh.new(); pm.size = Vector2(size, size)
	mi.mesh = pm; mi.material_override = pm_mat
	sb.add_child(mi)

	var cs    = CollisionShape3D.new()
	var shape = WorldBoundaryShape3D.new()   # infinite flat plane at Y=0
	cs.shape  = shape
	sb.add_child(cs)

	sb.name = "Ground"
	add_child(sb)

func _spawn_prop(pd: Dictionary) -> void:
	var shape = str(pd.get("shape", "box"))
	var sz_d  = pd.get("size", {"x":1,"y":1,"z":1})
	var sz    = Vector3(float(sz_d.get("x",1)), float(sz_d.get("y",1)), float(sz_d.get("z",1)))
	var pos_d = pd.get("position", {"x":0,"y":0,"z":0})
	var color = _c(pd.get("color", {"r":0.6,"g":0.5,"b":0.4}), 0.6, 0.5, 0.4)

	var mi  = MeshInstance3D.new()
	var mat = StandardMaterial3D.new()
	mat.albedo_color = color
	mi.material_override = mat

	match shape:
		"sphere":
			var sm = SphereMesh.new()
			sm.radius = sz.x * 0.5; sm.height = sz.x
			mi.mesh = sm
		"cylinder":
			var cm = CylinderMesh.new()
			cm.top_radius = sz.x * 0.5; cm.bottom_radius = sz.x * 0.5; cm.height = sz.y
			mi.mesh = cm
		_:
			var bm = BoxMesh.new(); bm.size = sz
			mi.mesh = bm

	mi.position = Vector3(float(pos_d.get("x",0)), float(pos_d.get("y",0)), float(pos_d.get("z",0)))
	mi.name = str(pd.get("id", "prop_%d" % randi()))
	add_child(mi)

# ──────────────────────────────────────────────
# Actor spawning
# ──────────────────────────────────────────────

func _spawn_actors(data: Dictionary) -> void:
	# Build lookup: actor_id -> physics descriptor
	var phys_map: Dictionary = {}
	for pd in data.get("physics_objects", []):
		phys_map[str(pd.get("actor_id", ""))] = pd

	var actors = data.get("actors", [])
	for actor_data in actors:
		var id   = str(actor_data.get("id", "actor_%d" % randi()))
		var type = str(actor_data.get("type", "box"))
		var pos_d = actor_data.get("initial_position", {"x":0,"y":0,"z":0})
		var rot_d = actor_data.get("initial_rotation", {"x":0,"y":0,"z":0})
		var pos   = Vector3(float(pos_d.get("x",0)), float(pos_d.get("y",0)), float(pos_d.get("z",0)))
		var rot   = Vector3(float(rot_d.get("x",0)), float(rot_d.get("y",0)), float(rot_d.get("z",0)))

		var phys = phys_map.get(id, {})
		var body_type = str(phys.get("body_type", "none"))
		
		# Always create visual from manifest/composite first
		var visual: Node3D = _create_actor_visual(id, type)

		if body_type == "rigid":
			var node = _create_rigid_actor(id, pos, rot, phys, visual)
			add_child(node)
			print("Spawned RIGID: ", id)
		elif body_type == "static":
			var node = _create_static_actor(id, pos, rot, phys, visual)
			add_child(node)
			print("Spawned STATIC: ", id)
		else:
			visual.name             = id
			visual.position         = pos
			visual.rotation_degrees = rot
			add_child(visual)
			print("Spawned: ", id)


	# ── Attachment pass: reparent attached actors to their parent ──────────────
	# Done after all actors are spawned so parent nodes exist.
	for actor_data in actors:
		var child_id  = str(actor_data.get("id", ""))
		var parent_id = str(actor_data.get("attach_to", ""))
		if parent_id == "" or not has_node(NodePath(child_id)) or not has_node(NodePath(parent_id)):
			continue

		var child_node  = get_node(NodePath(child_id))
		var parent_node = get_node(NodePath(parent_id))

		# Apply local offset
		var off_d = actor_data.get("local_offset", {"x":0,"y":0,"z":0})
		var offset = Vector3(float(off_d.get("x",0)), float(off_d.get("y",0)), float(off_d.get("z",0)))

		# Reparent: move child under parent node
		remove_child(child_node)
		parent_node.add_child(child_node)
		child_node.position         = offset
		child_node.rotation_degrees = Vector3.ZERO
		print("Attached '", child_id, "' -> '", parent_id, "' at offset ", offset)

func _create_actor_visual(id: String, type: String) -> Node3D:
	# Try manifest first
	var entry = _asset_manifest.get(id, null)
	if entry != null and typeof(entry) == TYPE_DICTIONARY:
		if str(entry.get("type", "")) == "composite":
			var parts = entry.get("parts", [])
			if typeof(parts) == TYPE_ARRAY and parts.size() > 0:
				print("Building composite actor for ", id)
				return _build_composite_actor(parts)
		var res_path = str(entry.get("path", ""))
		var target   = entry.get("target_size", {"x":1,"y":1,"z":1})
		if res_path != "":
			var glb = _load_glb_model(res_path)
			if glb != null:
				_normalize_model(glb, target)
				print("Loaded GLB for ", id, ": ", res_path)
				return glb
			else:
				print("GLB load failed for ", id, ", falling back to box")
	# Ultimate fallback: simple box if manifest failed
	return _create_box(Vector3(1,1,1), Color.GRAY)


func _build_composite_actor(parts: Array) -> Node3D:
	var root = Node3D.new()
	var nodes: Dictionary = {"": root} # Map for parent resolution

	# First pass: Create all nodes
	for p in parts:
		if typeof(p) != TYPE_DICTIONARY: continue
		var p_name = str(p.get("name", "part_%d" % nodes.size()))
		var shape = str(p.get("shape", "box"))
		var size  = _v3(p.get("size", {"x":1,"y":1,"z":1}), 1, 1, 1)
		var pos   = _v3(p.get("position", {"x":0,"y":0,"z":0}), 0, 0, 0)
		var rot_d = p.get("rotation", {"x":0,"y":0,"z":0})
		var rot   = Vector3(float(rot_d.get("x",0)), float(rot_d.get("y",0)), float(rot_d.get("z",0)))
		var col   = _c(p.get("color", {"r":0.8,"g":0.8,"b":0.8}), 0.8, 0.8, 0.8)
		
		var mi = MeshInstance3D.new()
		mi.name = p_name
		var mat = _make_mat(col)
		mi.material_override = mat
		
		match shape:
			"sphere":
				var sm = SphereMesh.new(); sm.radius = size.x * 0.5; sm.height = size.x
				mi.mesh = sm
			"cylinder":
				var cm = CylinderMesh.new(); cm.top_radius = size.x * 0.5; cm.bottom_radius = size.x * 0.5; cm.height = size.y
				mi.mesh = cm
			_:
				var bm = BoxMesh.new(); bm.size = size
				mi.mesh = bm
		
		mi.position = pos
		mi.rotation_degrees = rot
		nodes[p_name] = mi

	# Second pass: Link hierarchy
	for p in parts:
		var p_name = str(p.get("name", ""))
		var parent_name = str(p.get("parent_name", ""))
		if p_name == "": continue
		var node = nodes[p_name]
		var parent = nodes.get(parent_name, root)
		if parent != node:
			parent.add_child(node)
		else:
			root.add_child(node)
			
	return root


# ── GLB Runtime Loader ────────────────────────────────────────────────────────

func _load_glb_model(res_path: String) -> Node3D:
	var abs_path = ProjectSettings.globalize_path("res://" + res_path) \
				   if not res_path.begins_with("res://") \
				   else ProjectSettings.globalize_path(res_path)
	if not FileAccess.file_exists(abs_path):
		print("[AssetLoader] Not found: ", abs_path)
		return null
	var doc   = GLTFDocument.new()
	var state = GLTFState.new()
	var err   = doc.append_from_file(abs_path, state)
	if err != OK:
		print("[AssetLoader] Parse error ", err, " for ", abs_path)
		return null
	return doc.generate_scene(state)

func _normalize_model(node: Node3D, target_size: Dictionary) -> void:
	var tx = float(target_size.get("x", 1.0))
	var ty = float(target_size.get("y", 1.0))
	var tz = float(target_size.get("z", 1.0))
	# Measure AABB in local space via recursive pass
	var state = [AABB(), false]
	_collect_aabb(node, Transform3D.IDENTITY, state)
	var aabb: AABB = state[0]
	if not state[1] or aabb.size == Vector3.ZERO:
		return
	var sx = tx / max(aabb.size.x, 0.001)
	var sy = ty / max(aabb.size.y, 0.001)
	var sz = tz / max(aabb.size.z, 0.001)
	var s  = min(sx, min(sy, sz))
	node.scale = Vector3.ONE * s
	# Shift bottom of model to Y=0 and centre X/Z
	node.position = Vector3(
		-aabb.get_center().x * s,
		-aabb.position.y * s,
		-aabb.get_center().z * s)

func _collect_aabb(node: Node3D, xform: Transform3D, state: Array) -> void:
	var local_xform = xform * node.transform
	if node is MeshInstance3D and node.mesh != null:
		var mesh_aabb = local_xform * node.mesh.get_aabb()
		if state[1]:
			state[0] = state[0].merge(mesh_aabb)
		else:
			state[0] = mesh_aabb
			state[1] = true
	for child in node.get_children():
		if child is Node3D:
			_collect_aabb(child, local_xform, state)

# ── Physics actor helpers ─────────────────────────────────────────────────────

func _make_collision_shape(visual: Node3D, cshape: String) -> CollisionShape3D:
	var cs    = CollisionShape3D.new()
	var shape: Shape3D
	
	# Try to find a good size from the visual's AABB
	var state = [AABB(), false]
	_collect_aabb(visual, Transform3D.IDENTITY, state)
	var aabb: AABB = state[0]
	var size = aabb.size if state[1] and aabb.size != Vector3.ZERO else Vector3(1,1,1)

	match cshape:
		"sphere":
			var s = SphereShape3D.new(); s.radius = max(size.x, size.z) * 0.5
			shape = s
		"capsule":
			var s = CapsuleShape3D.new(); s.radius = max(size.x, size.z) * 0.4; s.height = size.y
			shape = s
		_:  # box
			var s = BoxShape3D.new(); s.size = size
			shape = s
	cs.shape = shape
	return cs


func _create_rigid_actor(id: String, pos: Vector3, rot: Vector3, phys: Dictionary, visual: Node3D) -> RigidBody3D:
	var rb  = RigidBody3D.new()
	rb.name = id
	rb.position         = pos
	rb.rotation_degrees = rot

	var pm_res = PhysicsMaterial.new()
	pm_res.friction = float(phys.get("friction", 0.6))
	pm_res.bounce   = float(phys.get("bounce",   0.2))
	rb.physics_material_override = pm_res
	rb.mass          = float(phys.get("mass",          70.0))
	rb.gravity_scale = float(phys.get("gravity_scale", 1.0))

	rb.add_child(visual)
	rb.add_child(_make_collision_shape(visual, str(phys.get("collision_shape", "box"))))

	var lv_d = phys.get("initial_linear_velocity",  {"x":0,"y":0,"z":0})
	var av_d = phys.get("initial_angular_velocity", {"x":0,"y":0,"z":0})
	rb.linear_velocity  = Vector3(float(lv_d.get("x",0)), float(lv_d.get("y",0)), float(lv_d.get("z",0)))
	rb.angular_velocity = Vector3(float(av_d.get("x",0)), float(av_d.get("y",0)), float(av_d.get("z",0)))
	return rb

func _create_static_actor(id: String, pos: Vector3, rot: Vector3, phys: Dictionary, visual: Node3D) -> StaticBody3D:
	var sb  = StaticBody3D.new()
	sb.name = id
	sb.position         = pos
	sb.rotation_degrees = rot
	sb.add_child(visual)
	sb.add_child(_make_collision_shape(visual, str(phys.get("collision_shape", "box"))))
	return sb


func _create_box(size: Vector3, color: Color) -> Node3D:
	var mi  = MeshInstance3D.new()
	var box = BoxMesh.new()
	box.size = size
	mi.mesh  = box
	var mat = StandardMaterial3D.new()
	mat.albedo_color = color
	mi.material_override = mat
	return mi

func _make_mat(c: Color, rough: float = 0.6, metal: float = 0.0) -> StandardMaterial3D:
	var m = StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness    = rough
	m.metallic     = metal
	return m

func _add_box(root: Node3D, mat: StandardMaterial3D, size: Vector3, pos: Vector3, rot_deg: Vector3 = Vector3.ZERO) -> void:
	var mi = MeshInstance3D.new()
	var bm = BoxMesh.new(); bm.size = size
	mi.mesh = bm; mi.material_override = mat
	mi.position = pos; mi.rotation_degrees = rot_deg
	root.add_child(mi)

func _add_sphere(root: Node3D, mat: StandardMaterial3D, radius: float, pos: Vector3) -> void:

# ──────────────────────────────────────────────
# Animation building
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Animation building
# ──────────────────────────────────────────────

func _build_animation(data: Dictionary) -> void:
	var anim = Animation.new()
	var meta = data.get("meta", {"total_duration": 5.0, "fps": 60})
	anim.length = float(meta.get("total_duration", 5.0))
	anim.step   = 1.0 / float(meta.get("fps", 60))

	# Camera is handled by _process() runtime tracker — not keyframed here.

	var actor_tracks = data.get("actor_tracks", {})
	# Build attach map for path resolution
	for actor_data in data.get("actors", []):
		var cid = str(actor_data.get("id", ""))
		var pid = str(actor_data.get("attach_to", ""))
		if pid != "":
			_attach_map[cid] = pid

	for actor_id in actor_tracks:
		# Resolve node path — attached actors live under their parent node
		var node_path: String
		if _attach_map.has(actor_id):
			var parent_id = _attach_map[actor_id]
			node_path = parent_id + "/" + actor_id
		else:
			node_path = actor_id

		if not has_node(NodePath(node_path)):
			print("Warning: no node for actor track: ", node_path)
			continue
		var node = get_node(NodePath(node_path))
		if node is RigidBody3D:
			print("Skipping keyframes for physics body: ", actor_id)
			continue  # physics engine controls this actor
		_build_node_track(anim, node_path, actor_tracks[actor_id], false)

	var library: AnimationLibrary
	if animation_player.has_animation_library(""):
		library = animation_player.get_animation_library("")
	else:
		library = AnimationLibrary.new()
		animation_player.add_animation_library("", library)
	library.add_animation("director_cut", anim)

func _build_node_track(anim: Animation, node_path: String, track_data: Array, is_camera: bool) -> void:
	var pos_idx = anim.add_track(Animation.TYPE_POSITION_3D)
	anim.track_set_path(pos_idx, node_path + ":position")

	var rot_idx = anim.add_track(Animation.TYPE_ROTATION_3D)
	anim.track_set_path(rot_idx, node_path + ":quaternion")

	# Sub-track management: part_name -> {pos_idx, rot_idx}
	var sub_indices: Dictionary = {}

	for key in track_data:
		var time = float(key.get("time", 0.0))

		var pd: Dictionary
		var rd: Dictionary
		if is_camera:
			var trans = key.get("transform", {})
			pd = trans.get("position", {"x":0,"y":1,"z":5})
			rd = trans.get("rotation", {"x":0,"y":0,"z":0})
		else:
			pd = key.get("position", {"x":0,"y":0,"z":0})
			rd = key.get("rotation", {"x":0,"y":0,"z":0})

		anim.position_track_insert_key(pos_idx, time,
			Vector3(float(pd.get("x",0)), float(pd.get("y",0)), float(pd.get("z",0))))

		var euler = Vector3(
			deg_to_rad(float(rd.get("x",0))),
			deg_to_rad(float(rd.get("y",0))),
			deg_to_rad(float(rd.get("z",0))))
		anim.rotation_track_insert_key(rot_idx, time, Quaternion.from_euler(euler))
		
		# Handle sub_tracks for composite parts
		var sub_tracks = key.get("sub_tracks", {})
		for part_name in sub_tracks:
			if not sub_indices.has(part_name):
				var p_path = node_path + "/" + part_name
				var p_pos_idx = anim.add_track(Animation.TYPE_POSITION_3D)
				anim.track_set_path(p_pos_idx, p_path + ":position")
				var p_rot_idx = anim.add_track(Animation.TYPE_ROTATION_3D)
				anim.track_set_path(p_rot_idx, p_path + ":quaternion")
				sub_indices[part_name] = {"pos": p_pos_idx, "rot": p_rot_idx}
			
			var sdata = sub_tracks[part_name]
			var sp = sdata.get("position", {"x":0,"y":0,"z":0})
			var sr = sdata.get("rotation", {"x":0,"y":0,"z":0})
			
			anim.position_track_insert_key(sub_indices[part_name].pos, time,
				Vector3(float(sp.get("x",0)), float(sp.get("y",0)), float(sp.get("z",0))))
			
			var seur = Vector3(deg_to_rad(float(sr.get("x",0))), deg_to_rad(float(sr.get("y",0))), deg_to_rad(float(sr.get("z",0))))
			anim.rotation_track_insert_key(sub_indices[part_name].rot, time, Quaternion.from_euler(seur))

	anim.track_set_interpolation_type(pos_idx, Animation.INTERPOLATION_CUBIC)
	anim.track_set_interpolation_type(rot_idx, Animation.INTERPOLATION_CUBIC)
	for part_name in sub_indices:
		anim.track_set_interpolation_type(sub_indices[part_name].pos, Animation.INTERPOLATION_CUBIC)
		anim.track_set_interpolation_type(sub_indices[part_name].rot, Animation.INTERPOLATION_CUBIC)


func _on_animation_finished(_anim_name: String):
	print("Cut! Animation finished. Rendering complete.")
	get_tree().quit()

