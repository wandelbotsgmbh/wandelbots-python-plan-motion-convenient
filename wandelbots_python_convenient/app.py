import copy
from typing import List

from decouple import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from loguru import logger

from wandelbots import MotionGroup, Planner
from wandelbots.types import Pose, CommandSettings
from wandelbots.apis import motion_group as motion_group_api
from wandelbots.apis import motion_group_infos as motion_group_infos_api

from wandelbots_python_convenient.utils import CELL_ID, get_api_client

BASE_PATH = config("BASE_PATH", default="", cast=str)
app = FastAPI(title="wandelbots_python_convenient", root_path=BASE_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", summary="Redirects to the swagger docs page")
async def root():
    # One could serve a nice UI here as well. For simplicity, we just redirect to the swagger docs page.
    return RedirectResponse(url=BASE_PATH + "/docs")


@app.get("/app_icon.png", summary="Services the app icon for the homescreen")
async def get_app_icon():
    try:
        return FileResponse(path="static/app_icon.png", media_type='image/png')
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Icon not found")


@app.post(
    "/move_robot",
    status_code=201,
    summary="Moves the robot in a rectangle",
    description="Example calculates a path based on user input(parameters), plans the path and executes the motion.")
async def move_robot(offset_mm: int):
    logger.info("verifying user input...")

    if offset_mm < 0 or offset_mm > 1000:
        raise HTTPException(status_code=400, detail="offset must be between 0 and 100")

    logger.info("creating api clients...")

    my_instance = get_api_client()
    motion_groups = motion_group_api.get_active_motion_groups(instance=my_instance, cell=CELL_ID)

    if len(motion_groups) != 1:
        raise HTTPException(
            status_code=400,
            detail="No or more than one motion group found. Example just works with one motion group. "
                   "Go to settings app and create one or delete all except one.")

    motion_group_id = motion_groups[0]
    logger.info("using motion group {}", motion_group_id)

    tcps = motion_group_infos_api.get_tcps(instance=my_instance, cell=CELL_ID, motion_group=motion_group_id)
    tcp = tcps[0]

    logger.info("using active tcp {}",tcp)

    my_motion_group = MotionGroup(
        instance=my_instance,
        cell=CELL_ID,
        motion_group=motion_group_id,
        default_tcp=tcp,
    )

    logger.info("calculating path...")

    initial_joints = my_motion_group.current_joints()
    initial_pose = my_motion_group.current_tcp_pose()
    planner = Planner(my_motion_group)

    poses = calculate_points(initial_pose, offset_mm)

    settings = CommandSettings(position_blending=10)

    trajectory = [
        planner.jptp(joints=initial_joints),
        *[
            planner.line(pose=pose, settings=settings)
            for pose in poses
        ],
        planner.jptp(joints=initial_joints),
    ]

    plan_result = planner.plan(
        start_joints=my_motion_group.current_joints(), trajectory=trajectory, tcp=tcp
    )

    if plan_result is None:
        raise HTTPException(
            status_code=500,
            detail="Planning failed."
                   " Check that the starting position provides enough space for moving with the desired offset."
                   )

    logger.info("start moving...")

    async for state in my_motion_group.execute_motion_stream_async(motion=plan_result.motion, speed=25, response_rate_ms=500):
        current_location = state.current_location_on_trajectory
        print(f"Current Location: {current_location}")

    logger.info("Moving done. Closing client...")


def calculate_points(initial: Pose, offset_mm: int) -> List[Pose]:
    # simple rectangle. Positions in mm
    pos1 = copy.deepcopy(initial)
    pos1.position.x = pos1.position.x + offset_mm

    pos2 = copy.deepcopy(pos1)
    pos2.position.y = pos2.position.y + offset_mm

    pos3 = copy.deepcopy(pos2)
    pos3.position.x = pos3.position.x - offset_mm

    pos4 = copy.deepcopy(pos3)
    pos4.position.y = pos4.position.y - offset_mm

    return [initial, pos1, pos2, pos3, pos4, initial]