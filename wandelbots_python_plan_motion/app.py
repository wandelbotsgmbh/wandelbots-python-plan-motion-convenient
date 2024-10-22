import copy
from typing import List

import wandelbots_api_client as wb
from decouple import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from loguru import logger

from wandelbots_python_plan_motion.utils import CELL_ID
from wandelbots_python_plan_motion.utils import get_api_client


BASE_PATH = config("BASE_PATH", default="", cast=str)
app = FastAPI(title="wandelbots_python_plan_motion", root_path=BASE_PATH)

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
    client = get_api_client()
    motion_group_info_api = wb.MotionGroupInfosApi(api_client=client)
    motion_group_api = wb.MotionGroupApi(api_client=client)
    move_api = wb.MotionApi(api_client=client)

    logger.info("selecting motion group...")
    motion_groups = await motion_group_api.list_motion_groups(cell=CELL_ID)

    if len(motion_groups.instances) != 1:
        raise HTTPException(
            status_code=400,
            detail="No or more than one motion group found. Example just works with one motion group. "
                   "Go to settings app and create one or delete all except one.")

    motion_group_id = motion_groups.instances[0].motion_group
    logger.info("using motion group {}", motion_group_id)
    active_tcp = await motion_group_info_api.get_active_tcp(cell=CELL_ID, motion_group=motion_group_id)
    logger.info("using active tcp {}", active_tcp.id)

    logger.info("activating motion groups...")
    await motion_group_api.activate_motion_group(
        cell=CELL_ID,
        motion_group=motion_group_id)

    robot_state = await motion_group_info_api.get_current_motion_group_state(
        cell=CELL_ID,
        motion_group=motion_group_id,
        tcp=active_tcp.id)

    logger.info("calculating path...")
    initial_pose = wb.models.Pose(position=robot_state.tcp_pose.position, orientation=robot_state.tcp_pose.orientation)
    plan_request = get_plan_request(
        offset_mm=offset_mm,
        motion_group_id=motion_group_id,
        initial_pose=initial_pose,
        initial_joints=robot_state.state.joint_position)
    plan_response = await move_api.plan_motion(cell=CELL_ID, plan_request=plan_request)

    if plan_response.plan_successful_response is None:
        failure = get_planning_failure(plan_response)
        raise HTTPException(
            status_code=500,
            detail="Planning failed."
                   " Check that the starting position provides enough space for moving with the desired offset."
                   f" detailed message: {failure}")

    move_request = wb.models.MoveRequest(playback_speed_in_percent=100)

    logger.info("start moving...")
    async for response in move_api.stream_move_forward(cell=CELL_ID,
                                                       motion=plan_response.plan_successful_response.motion,
                                                       request=move_request):
        pass

    logger.info("Moving done. Closing client...")
    await client.close()


def get_plan_request(offset_mm, motion_group_id, initial_pose, initial_joints) -> wb.models.PlanRequest:
    moves = []
    for pose in calculate_points(initial_pose, offset_mm):
        moves.append(linear_move(pose))
    return wb.models.PlanRequest(
        motion_group=motion_group_id,
        commands=moves,
        start_joint_position=initial_joints,
    )


def linear_move(pose: wb.models.Pose) -> wb.models.Command:
    settings = wb.models.CommandSettings()
    # blending in mm
    settings.position_blending = 20
    return wb.models.Command(line=pose, settings=settings)


def calculate_points(initial: wb.models.Pose, offset_mm: int) -> List[wb.models.Pose]:
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


def get_planning_failure(plan_response: wb.models.PlanResponse) -> str:
    if plan_response.plan_failed_response is not None:
        return plan_response.plan_failed_response.description
    if plan_response.plan_failed_on_trajectory_response is not None:
        return plan_response.plan_failed_on_trajectory_response.description
    return "unknown planning failure"
