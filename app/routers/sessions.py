from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from aiortc.contrib.media import MediaRelay
from app.dependencies import templates
from app.services.webrtc import handle_offer, handle_ice_candidate

router = APIRouter(
    prefix="/session",
    tags=["Session"]
)


class SessionManager:
    def __init__(self):
        self.active_connections: dict[str, dict] = {}
        self.relay = MediaRelay()
        '''
        active_connections structure:
        {
            "session-123": {
                "state": "waiting" | "live" | "ended",
                "teacher": {
                    "name": "Guru",
                    "socket": <WebSocket>,
                    "peer_connection": <RTCPeerConnection>,
                    "tracks": [audio_track, video_track]
                },
                "students": [
                    {
                        "name": "Student 1",
                        "socket": <WebSocket>,
                        "peer_connection": <RTCPeerConnection>
                    }
                ]
            }
        }
        '''

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        role: str,
        name: str
    ):
        await websocket.accept()

        # create session if it doesn't exist yet
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {
                "state": "waiting",
                "teacher": None,
                "students": []
            }

        if role == "teacher":
            # always fresh start when teacher connects or reconnects
            # clear old tracks so stale data never causes problems
            self.active_connections[session_id]["teacher"] = {
                "name": name,
                "socket": websocket,
                "peer_connection": None,
                "tracks": []
            }
            # reset state to waiting until tracks actually arrive
            self.active_connections[session_id]["state"] = "waiting"

        if role == "student":
            self.active_connections[session_id]["students"].append({
                "name": name,
                "socket": websocket,
                "peer_connection": None
            })

    def disconnect(self, websocket: WebSocket, session_id: str, role: str):
        if session_id not in self.active_connections:
            return

        if role == "teacher":
            # teacher left — clear their data, mark session ended
            self.active_connections[session_id]["teacher"] = None
            self.active_connections[session_id]["state"] = "ended"

        else:
            # remove only the student who disconnected
            # other students are NOT affected
            self.active_connections[session_id]["students"] = [
                s for s in self.active_connections[session_id]["students"]
                if s["socket"] != websocket
            ]

        # clean up session only if completely empty
        session = self.active_connections[session_id]
        if session["teacher"] is None and len(session["students"]) == 0:
            del self.active_connections[session_id]
            print(f"Session {session_id} cleaned up")

    def store_peer_connection(
        self,
        session_id: str,
        role: str,
        websocket: WebSocket,
        pc
    ):
        if session_id not in self.active_connections:
            return

        if role == "teacher":
            teacher = self.active_connections[session_id].get("teacher")
            if teacher:
                teacher["peer_connection"] = pc

        else:
            for student in self.active_connections[session_id]["students"]:
                if student["socket"] == websocket:
                    student["peer_connection"] = pc
                    break

    def store_teacher_track(self, session_id: str, track):
        '''
        Store one raw track at a time.
        Called twice — once for audio, once for video.
        Prevents duplicates by checking kind.
        '''
        if session_id not in self.active_connections:
            return
        teacher = self.active_connections[session_id].get("teacher")
        if teacher is None:
            return

        # prevent duplicate tracks by kind
        existing_kinds = [t.kind for t in teacher["tracks"]]
        if track.kind not in existing_kinds:
            teacher["tracks"].append(track)
            print(f"Track stored — kind: {track.kind}, total: {len(teacher['tracks'])}")

    def get_teacher_tracks_for_student(self, session_id: str) -> list:
        '''
        Each student gets their OWN relay subscription.
        MediaRelay isolates students from each other —
        one student refreshing never affects other students.
        '''
        if session_id not in self.active_connections:
            return []
        teacher = self.active_connections[session_id].get("teacher")
        if teacher is None:
            return []
        raw_tracks = teacher.get("tracks", [])

        # fresh independent subscription for each student
        return [
            self.relay.subscribe(track, buffered=False)
            for track in raw_tracks
        ]

    def get_students(self, session_id: str) -> list:
        if session_id not in self.active_connections:
            return []
        return self.active_connections[session_id]["students"]

    def get_state(self, session_id: str) -> str:
        if session_id not in self.active_connections:
            return "waiting"
        return self.active_connections[session_id].get("state", "waiting")

    def set_state(self, session_id: str, state: str):
        if session_id in self.active_connections:
            self.active_connections[session_id]["state"] = state
            print(f"Session {session_id} state → {state}")

    async def notify_students(self, session_id: str, message: dict):
        '''
        Send a message to all students in a session.
        Used to notify when teacher joins or leaves.
        '''
        students = self.get_students(session_id)
        for student in students:
            try:
                await student["socket"].send_json(message)
            except Exception as e:
                print(f"Failed to notify student {student['name']} — {e}")


session_manager = SessionManager()


# ─── routes ───────────────────────────────────────────────────────────────────

@router.get("/join")
async def join_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": "SevakStream"}
    )


@router.get("/{session_id}")
async def room_page(
    request: Request,
    session_id: str,
    role: str,
    name: str
):
    return templates.TemplateResponse(
        request=request,
        name="room.html",
        context={
            "app_name": "SevakStream",
            "session_id": session_id,
            "role": role,
            "name": name
        }
    )


@router.websocket("/ws/{session_id}")
async def session_websocket(
    websocket: WebSocket,
    session_id: str,
    role: str,
    name: str
):
    await session_manager.connect(websocket, session_id, role, name)
    pc = None
    recorder = None

    # tell this client the current session state immediately
    # teacher gets "waiting", student gets current state
    await websocket.send_json({
        "type": "session-state",
        "state": session_manager.get_state(session_id)
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "offer":
                pc, recorder = await handle_offer(
                    data=data,
                    websocket=websocket,
                    session_id=session_id,
                    role=role,
                    store_track_callback=lambda track: session_manager.store_teacher_track(
                        session_id, track
                    ),
                    get_teacher_tracks_callback=lambda: session_manager.get_teacher_tracks_for_student(
                        session_id
                    ),
                    notify_students_callback=lambda: session_manager.notify_students(
                        session_id,
                        {"type": "session-state", "state": "live"}
                    )
                )
                session_manager.store_peer_connection(
                    session_id=session_id,
                    role=role,
                    websocket=websocket,
                    pc=pc
                )

                # mark session live when teacher's offer is processed
                if role == "teacher":
                    session_manager.set_state(session_id, "live")

            elif msg_type == "ice-candidate":
                await handle_ice_candidate(data, pc)

            elif msg_type == "get-state":
                # client asking for current state — send it
                await websocket.send_json({
                    "type": "session-state",
                    "state": session_manager.get_state(session_id)
                })

            else:
                print(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        # stop recording if teacher left
        if recorder:
            await recorder.stop()
            print(f"Recording saved — session {session_id}")

        # close peer connection
        if pc:
            await pc.close()

        # notify all students if teacher disconnected
        if role == "teacher":
            await session_manager.notify_students(
                session_id,
                {"type": "session-state", "state": "ended"}
            )

        session_manager.disconnect(websocket, session_id, role)
        print(f"[{session_id}] {role} — {name} disconnected")