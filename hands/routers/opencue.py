from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/opencue")


class RerouteRequest(BaseModel):
    job_id: str
    target_node: str


class RequeueRequest(BaseModel):
    job_id: str
    frame: int


class KillRequest(BaseModel):
    job_id: str


@router.post("/reroute")
async def reroute_job(req: RerouteRequest):
    return {
        "status": "success",
        "action": "reroute",
        "job_id": req.job_id,
        "target_node": req.target_node,
        "message": f"Job {req.job_id} rerouted to {req.target_node}",
    }


@router.post("/requeue")
async def requeue_job(req: RequeueRequest):
    return {
        "status": "success",
        "action": "requeue",
        "job_id": req.job_id,
        "frame": req.frame,
    }


@router.post("/kill")
async def kill_job(req: KillRequest):
    return {
        "status": "success",
        "action": "kill",
        "job_id": req.job_id,
    }
