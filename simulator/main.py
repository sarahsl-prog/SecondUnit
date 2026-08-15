"""Simulator service."""
from fastapi import FastAPI, HTTPException
from simulator.engine import RenderFarmSimulator
from shared.logger import get_logger

app = FastAPI(title="SecondUnit Simulator")
simulator = RenderFarmSimulator(node_count=8)
logger = get_logger(agent_name="Simulator")


@app.on_event("startup")
async def startup():
    simulator.start()


@app.on_event("shutdown")
async def shutdown():
    simulator.stop()


@app.post("/simulator/trigger/{scenario_name}")
async def trigger_failure(scenario_name: str, target_node: str = "", scene: str = ""):
    try:
        result = simulator.trigger_scenario(scenario_name, target_node, scene)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/simulator/reset")
async def reset_simulator():
    simulator.reset()
    return {"status": "reset"}


@app.get("/simulator/status")
async def get_status():
    return simulator.get_status()


@app.get("/simulator/jobs")
async def get_jobs(node: str = "", status: str = ""):
    """Real job state for Pathologist to derive affected_frames/scene from
    (review #10), instead of those being hardcoded in Brain."""
    jobs = simulator.jobs
    if node:
        jobs = [j for j in jobs if j.assigned_node == node]
    if status:
        jobs = [j for j in jobs if j.status == status]
    return {"jobs": [j.model_dump() for j in jobs]}


@app.get("/health")
async def health():
    return {"status": "healthy"}
