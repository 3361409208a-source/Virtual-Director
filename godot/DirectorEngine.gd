extends Node3D

@onready var animation_player = $AnimationPlayer
@onready var camera = $Camera3D

const HUMANOID_COLORS = [
	Color(0.27, 0.52, 0.90),  # blue
	Color(0.92, 0.26, 0.21),  # red
	Color(0.18, 0.72, 0.34),  # green
	Color(0.97, 0.76, 0.10),  # yellow
	Color(0.65, 0.20, 0.85),  # purple
	Color(0.10, 0.78, 0.88),  # cyan
]
const CAR_COLORS = [
	Color(0.90, 0.20, 0.10),
	Color(0.10, 0.30, 0.85),
	Color(0.08, 0.55, 0.20),
	Color(0.95, 0.85, 0.10),
	Color(0.15, 0.15, 0.15),
	Color(0.90, 0.90, 0.90),
]

var _humanoid_idx := 0
var _car_idx       := 0

# Runtime camera tracking state
var _cam_track: Array    = []
var _cam_seg_idx: int    = 0
var _seg_start_t: float  = 0.0
var _orbit_angle: float  = 0.0
var _asset_manifest: Dictionary = {}  # actor_id → {path, target_size} | null

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

		if body_type == "rigid":
			var node = _create_rigid_actor(type, id, pos, rot, phys)
			add_child(node)
			print("Spawned RIGID: ", id, " (", type, ")")
		elif body_type == "static":
			var node = _create_static_actor(type, id, pos, rot, phys)
			add_child(node)
			print("Spawned STATIC: ", id, " (", type, ")")
		else:
			var node: Node3D = _create_actor_visual(id, type)
			node.name             = id
			node.position         = pos
			node.rotation_degrees = rot
			add_child(node)
			print("Spawned: ", id, " (", type, ")")

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
				print("GLB load failed for ", id, ", falling back to procedural")
	# Procedural fallback
	match type:
		"humanoid": return _create_humanoid()
		"car":      return _create_car()
		"plane":    return _create_plane()
		_:          return _create_box(Vector3(1,1,1), Color.GRAY)

func _build_composite_actor(parts: Array) -> Node3D:
	var root = Node3D.new()
	for p in parts:
		if typeof(p) != TYPE_DICTIONARY: continue
		var shape = str(p.get("shape", "box"))
		var size  = _v3(p.get("size", {"x":1,"y":1,"z":1}), 1, 1, 1)
		var pos   = _v3(p.get("position", {"x":0,"y":0,"z":0}), 0, 0, 0)
		var rot_d = p.get("rotation", {"x":0,"y":0,"z":0})
		var rot   = Vector3(float(rot_d.get("x",0)), float(rot_d.get("y",0)), float(rot_d.get("z",0)))
		var col   = _c(p.get("color", {"r":0.8,"g":0.8,"b":0.8}), 0.8, 0.8, 0.8)
		
		var mat = _make_mat(col)
		match shape:
			"sphere":   _add_sphere(root, mat, size.x * 0.5, pos)
			"cylinder": _add_cyl(root, mat, size.x * 0.5, size.y, pos, rot)
			_:          _add_box(root, mat, size, pos, rot)
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

func _make_collision_shape(type: String, cshape: String) -> CollisionShape3D:
	var cs    = CollisionShape3D.new()
	var shape: Shape3D
	match cshape:
		"sphere":
			var s = SphereShape3D.new(); s.radius = 0.5
			shape = s
		"capsule":
			var s = CapsuleShape3D.new(); s.radius = 0.3; s.height = 1.5
			shape = s
		_:  # box — size depends on actor type
			var s = BoxShape3D.new()
			if   type == "car":      s.size = Vector3(2.0, 0.9, 4.5)
			elif type == "humanoid": s.size = Vector3(0.5, 1.8, 0.3)
			elif type == "plane":    s.size = Vector3(6.0, 2.5, 5.0)
			else:                    s.size = Vector3(1.0, 1.0, 1.0)
			shape = s
	cs.shape = shape
	return cs

func _create_rigid_actor(type: String, id: String, pos: Vector3, rot: Vector3, phys: Dictionary) -> RigidBody3D:
	var rb  = RigidBody3D.new()
	rb.name = id
	rb.position         = pos
	rb.rotation_degrees = rot

	# Physics material
	var pm_res = PhysicsMaterial.new()
	pm_res.friction = float(phys.get("friction", 0.6))
	pm_res.bounce   = float(phys.get("bounce",   0.2))
	rb.physics_material_override = pm_res
	rb.mass          = float(phys.get("mass",          70.0))
	rb.gravity_scale = float(phys.get("gravity_scale", 1.0))

	# Visual mesh as child
	var visual: Node3D
	match type:
		"humanoid": visual = _create_humanoid()
		"car":      visual = _create_car()
		"plane":    visual = _create_plane()
		_:          visual = _create_box(Vector3(1,1,1), Color.GRAY)
	rb.add_child(visual)

	# Collision shape
	rb.add_child(_make_collision_shape(type, str(phys.get("collision_shape", "box"))))

	# Initial velocities applied after spawn via call_deferred
	var lv_d = phys.get("initial_linear_velocity",  {"x":0,"y":0,"z":0})
	var av_d = phys.get("initial_angular_velocity", {"x":0,"y":0,"z":0})
	rb.linear_velocity  = Vector3(float(lv_d.get("x",0)), float(lv_d.get("y",0)), float(lv_d.get("z",0)))
	rb.angular_velocity = Vector3(float(av_d.get("x",0)), float(av_d.get("y",0)), float(av_d.get("z",0)))
	return rb

func _create_static_actor(type: String, id: String, pos: Vector3, rot: Vector3, phys: Dictionary) -> StaticBody3D:
	var sb  = StaticBody3D.new()
	sb.name = id
	sb.position         = pos
	sb.rotation_degrees = rot

	var visual: Node3D
	match type:
		"humanoid": visual = _create_humanoid()
		"car":      visual = _create_car()
		"plane":    visual = _create_plane()
		_:          visual = _create_box(Vector3(1,1,1), Color.GRAY)
	sb.add_child(visual)
	sb.add_child(_make_collision_shape(type, str(phys.get("collision_shape", "box"))))
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
	var mi = MeshInstance3D.new()
	var sm = SphereMesh.new(); sm.radius = radius; sm.height = radius * 2.0
	mi.mesh = sm; mi.material_override = mat; mi.position = pos
	root.add_child(mi)

func _add_cyl(root: Node3D, mat: StandardMaterial3D, r: float, h: float, pos: Vector3, rot_deg: Vector3 = Vector3.ZERO) -> void:
	var mi = MeshInstance3D.new()
	var cm = CylinderMesh.new(); cm.top_radius = r; cm.bottom_radius = r; cm.height = h
	mi.mesh = cm; mi.material_override = mat
	mi.position = pos; mi.rotation_degrees = rot_deg
	root.add_child(mi)

# ── Humanoid: full 14-part anatomy, Y=0 = ground, total height ≈ 1.80 ──────────
# Proportions (in metres):
#   feet 0–0.10 | shin 0.10–0.50 | thigh 0.50–0.85 | hips 0.83
#   waist 0.92 | chest 1.00–1.40 | shoulders 1.38
#   neck 1.42–1.56 | head 1.56–1.80
func _create_humanoid() -> Node3D:
	var body_c = HUMANOID_COLORS[_humanoid_idx % HUMANOID_COLORS.size()]
	_humanoid_idx += 1
	var skin_c  = Color(0.95, 0.76, 0.60)
	var mat     = _make_mat(body_c)
	var skin    = _make_mat(skin_c)
	var root    = Node3D.new()

	# Head
	_add_sphere(root, skin, 0.155, Vector3(0, 1.67, 0))
	# Neck
	_add_cyl(root, skin, 0.055, 0.13, Vector3(0, 1.52, 0))
	# Chest
	_add_box(root, mat, Vector3(0.46, 0.42, 0.22), Vector3(0, 1.20, 0))
	# Waist (narrow)
	_add_box(root, mat, Vector3(0.35, 0.16, 0.19), Vector3(0, 0.93, 0))
	# Hips
	_add_box(root, mat, Vector3(0.42, 0.15, 0.22), Vector3(0, 0.80, 0))

	# Arms (left = −X, right = +X)
	for sx in [-1.0, 1.0]:
		var ax = sx * 0.31
		# Shoulder cap
		_add_sphere(root, mat, 0.085, Vector3(sx * 0.27, 1.38, 0))
		# Upper arm
		_add_cyl(root, mat, 0.07, 0.28, Vector3(ax, 1.10, 0))
		# Elbow
		_add_sphere(root, skin, 0.065, Vector3(ax, 0.95, 0))
		# Forearm
		_add_cyl(root, mat, 0.058, 0.25, Vector3(ax, 0.74, 0))
		# Hand
		_add_box(root, skin, Vector3(0.11, 0.10, 0.065), Vector3(ax, 0.58, 0))

	# Legs (left = −X, right = +X)
	for sx in [-1.0, 1.0]:
		var lx = sx * 0.115
		# Thigh
		_add_box(root, mat, Vector3(0.18, 0.36, 0.18), Vector3(lx, 0.60, 0))
		# Knee
		_add_sphere(root, skin, 0.075, Vector3(lx, 0.41, 0.02))
		# Shin
		_add_box(root, mat, Vector3(0.14, 0.32, 0.14), Vector3(lx, 0.21, 0))
		# Ankle
		_add_sphere(root, skin, 0.062, Vector3(lx, 0.06, 0))
		# Foot
		_add_box(root, skin, Vector3(0.13, 0.09, 0.22), Vector3(lx, 0.045, 0.05))

	return root

# ── Car: sedan-style, Y=0 = ground, length ≈ 4.5, width ≈ 2.0, height ≈ 1.45 ──
func _create_car() -> Node3D:
	var body_c   = CAR_COLORS[_car_idx % CAR_COLORS.size()]
	_car_idx    += 1
	var root     = Node3D.new()

	var mat_body   = _make_mat(body_c,            0.4, 0.1)
	var mat_glass  = _make_mat(Color(0.55,0.75,0.85, 0.6), 0.05, 0.0)
	mat_glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var mat_wheel  = _make_mat(Color(0.12, 0.12, 0.12), 0.9)
	var mat_rim    = _make_mat(Color(0.80, 0.80, 0.82), 0.3, 0.8)
	var mat_bump   = _make_mat(body_c.darkened(0.25), 0.7)
	var mat_head   = _make_mat(Color(1.0, 0.98, 0.85), 0.1, 0.0)
	var mat_tail   = _make_mat(Color(0.95, 0.10, 0.10), 0.2, 0.0)
	var mat_rubber = _make_mat(Color(0.08, 0.08, 0.08), 0.95)

	# ── Main body (low chassis + hood/trunk) ──
	_add_box(root, mat_body,  Vector3(2.02, 0.48, 4.50), Vector3(0, 0.44, 0.0))

	# ── Cabin (upper box, slightly inset) ──
	_add_box(root, mat_body,  Vector3(1.76, 0.58, 2.35), Vector3(0, 1.01, 0.18))

	# ── Windshield (front, tilted) ──
	_add_box(root, mat_glass, Vector3(1.52, 0.60, 0.07), Vector3(0, 0.97, -0.96), Vector3(-22, 0, 0))
	# ── Rear window (tilted other way) ──
	_add_box(root, mat_glass, Vector3(1.52, 0.50, 0.07), Vector3(0, 0.97,  1.32), Vector3( 22, 0, 0))
	# ── Side windows (left and right) ──
	for sx in [-1.0, 1.0]:
		_add_box(root, mat_glass, Vector3(0.07, 0.38, 1.60), Vector3(sx * 0.88, 1.05, 0.18))

	# ── Front bumper ──
	_add_box(root, mat_bump,  Vector3(2.00, 0.28, 0.18), Vector3(0, 0.26, -2.33))
	# ── Rear bumper ──
	_add_box(root, mat_bump,  Vector3(2.00, 0.28, 0.18), Vector3(0, 0.26,  2.33))

	# ── Headlights (2) ──
	for sx in [-1.0, 1.0]:
		_add_box(root, mat_head, Vector3(0.42, 0.18, 0.06), Vector3(sx * 0.62, 0.58, -2.27))
	# ── Taillights (2) ──
	for sx in [-1.0, 1.0]:
		_add_box(root, mat_tail, Vector3(0.42, 0.15, 0.06), Vector3(sx * 0.62, 0.55,  2.27))

	# ── Door seam strips (decorative line) ──
	for sx in [-1.0, 1.0]:
		_add_box(root, mat_bump, Vector3(0.04, 0.06, 3.20), Vector3(sx * 1.01, 0.64, 0.0))

	# ── Wheels: tire + rim ──
	for xv in [-1.06, 1.06]:
		for zv in [-1.45, 1.45]:
			# Tire
			_add_cyl(root, mat_wheel, 0.36, 0.26, Vector3(xv, 0.37, zv), Vector3(0, 0, 90))
			# Rim inner disk
			_add_cyl(root, mat_rim,   0.22, 0.28, Vector3(xv, 0.37, zv), Vector3(0, 0, 90))
			# Hub cap
			_add_cyl(root, mat_rim,   0.06, 0.30, Vector3(xv, 0.37, zv), Vector3(0, 0, 90))
			# Rubber sidewall ring
			_add_cyl(root, mat_rubber, 0.36, 0.04, Vector3(xv, 0.37, zv), Vector3(0, 0, 90))

	return root

# ── Plane: simple procedural airplane ──
func _create_plane() -> Node3D:
	var body_c   = CAR_COLORS[_car_idx % CAR_COLORS.size()]
	_car_idx    += 1
	var root     = Node3D.new()

	var mat_body   = _make_mat(body_c, 0.4, 0.2)
	var mat_glass  = _make_mat(Color(0.2, 0.2, 0.2), 0.1, 0.8)
	var mat_wing   = _make_mat(body_c.lightened(0.2), 0.5)

	# Main fuselage
	_add_box(root, mat_body, Vector3(1.2, 1.2, 4.0), Vector3(0, 1.0, 0))
	# Cockpit / Nose
	_add_box(root, mat_glass, Vector3(0.8, 0.8, 1.0), Vector3(0, 1.2, -2.0))
	# Main wings
	_add_box(root, mat_wing, Vector3(6.0, 0.2, 1.5), Vector3(0, 1.0, -0.5))
	# Tail fin
	_add_box(root, mat_wing, Vector3(0.2, 1.5, 1.0), Vector3(0, 2.0, 1.5))
	# Rear stabilizers
	_add_box(root, mat_wing, Vector3(2.5, 0.1, 0.8), Vector3(0, 1.2, 1.6))

	return root

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
	for actor_id in actor_tracks:
		if not has_node(NodePath(actor_id)):
			print("Warning: no node for actor track: ", actor_id)
			continue
		var node = get_node(NodePath(actor_id))
		if node is RigidBody3D:
			print("Skipping keyframes for physics body: ", actor_id)
			continue  # physics engine controls this actor
		_build_node_track(anim, actor_id, actor_tracks[actor_id], false)

	var library: AnimationLibrary
	if animation_player.has_animation_library(""):
		library = animation_player.get_animation_library("")
	else:
		library = AnimationLibrary.new()
		animation_player.add_animation_library("", library)
	library.add_animation("director_cut", anim)

func _build_node_track(anim: Animation, node_name: String, track_data: Array, is_camera: bool) -> void:
	var pos_idx = anim.add_track(Animation.TYPE_POSITION_3D)
	anim.track_set_path(pos_idx, node_name)

	var rot_idx = anim.add_track(Animation.TYPE_ROTATION_3D)
	anim.track_set_path(rot_idx, node_name)

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

	anim.track_set_interpolation_type(pos_idx, Animation.INTERPOLATION_CUBIC)
	anim.track_set_interpolation_type(rot_idx, Animation.INTERPOLATION_CUBIC)

func _on_animation_finished(_anim_name: String):
	print("Cut! Animation finished. Rendering complete.")
	get_tree().quit()

