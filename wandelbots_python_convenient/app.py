from decouple import config
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from loguru import logger

from nova import Nova
from nova.types import Pose
from nova.actions import MotionSettings, jnt, Linear

CELL_ID = config("CELL_ID", default="cell", cast=str)
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
        return FileResponse(path="static/app_icon.png", media_type="image/png")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Icon not found")


@app.post(
    "/move_robot",
    status_code=201,
    summary="Moves the robot in a rectangle",
    description="Example calculates a path based on user input(parameters), plans the path and executes the motion.",
)
async def move_robot(offset_mm: int):
    logger.info("verifying user input...")

    if offset_mm < 0 or offset_mm > 1000:
        raise HTTPException(status_code=400, detail="offset must be between 0 and 100")

    logger.info("creating api clients...")

    nova = Nova()
    cell = nova.cell(CELL_ID)
    controllers = await cell.controllers()
    controller = controllers[0]

    motion_groups = await controller.activated_motion_groups()
    if len(motion_groups) != 1:
        raise HTTPException(
            status_code=400,
            detail="No or more than one motion group found. Example just works with one motion group. "
            "Go to settings app and create one or delete all except one.",
        )

    async with controller[0] as motion_group:
        logger.info("using motion group {}", motion_group.motion_group_id)

        tcps = await motion_group.tcp_names()
        tcp = tcps[0]

        logger.info("using active tcp {}", tcp)
        logger.info("calculating path...")

        initial_joints = await motion_group.joints()
        initial_pose = await motion_group.tcp_pose(tcp)

        poses = calculate_points(initial_pose, offset_mm)
        actions = [
            jnt(initial_joints),
            *[Linear(target=pose, settings=MotionSettings(blending=10)) for pose in poses],
            jnt(initial_joints),
        ]

        joint_trajectory = await motion_group.plan(actions, tcp)
        if joint_trajectory is None:
            raise HTTPException(
                status_code=500,
                detail="Planning failed."
                " Check that the starting position provides enough space for moving with the desired offset.",
            )

        logger.info("start moving...")
        await motion_group.execute(joint_trajectory, tcp, actions=actions)
        logger.info("Moving done. Closing client...")


def calculate_points(initial: Pose, offset_mm: int) -> tuple[Pose, ...]:
    """Creates a simple rectangle. Positions in mm"""
    return (
        initial,
        initial @ (offset_mm, 0, 0, 0, 0, 0),
        initial @ (0, offset_mm, 0, 0, 0, 0),
        initial @ (-offset_mm, 0, 0, 0, 0, 0),
        initial @ (0, -offset_mm, 0, 0, 0, 0),
        initial,
    )
