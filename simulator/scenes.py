from pydantic import BaseModel


class Scene(BaseModel):
    name: str
    frame_count: int
    avg_render_time_sec: float
    memory_profile_gb: float


DEFAULT_SCENES = [
    Scene(name="scene_47", frame_count=2400, avg_render_time_sec=45.0, memory_profile_gb=8.0),
    Scene(name="scene_12", frame_count=1200, avg_render_time_sec=30.0, memory_profile_gb=4.0),
]
