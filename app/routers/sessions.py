from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from app.dependencies import templates
from app.services.webrtc import handle_ice_candidate, handle_offer 

router = APIRouter(
    prefix="/session",
    tags=['Session']
)

class SessionManager:
    def __init__(self):
        self.active_connections : dict[str, dict] = {}
        '''
        {
            "#session-123" : {
                "teacher" : {"socket": <WebSocket>, "name": "guru sevak singh", "peer_connection" : <RTCPeerConnectiono>},
                "students" : [
                    {"socket": <WebSocket, "name": "Student 1", "peer_connection" : <RTCPeerConnectiono>},
                    {"socket": <WebSocket, "name": "Student 1", "peer_connection" : <RTCPeerConnectiono>},
                    {"socket": <WebSocket, "name": "Student 1", "peer_connection" : <RTCPeerConnectiono>}
                ]
            }
        }
        '''
    
    async def connect(self, websocket : WebSocket, session_id: str, role : str, name : str):
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = {
                "teacher": None,
                "students": []
            }
        
        socket_data = {"name": name,
            'socket' : websocket,
            "peer_connection": None}
        
        if role == "teacher":
            self.active_connections[session_id]['teacher'] = socket_data

        if role == "student":
            self.active_connections[session_id]['students'].append(socket_data)

    def disconnect(self, websocket: WebSocket, session_id : str, role):
        if session_id not in self.active_connections:
            return
        
        if role == "teacher":
            self.active_connections[session_id]['teacher'] = None
        
        else:
            self.active_connections[session_id]['students'] = [sct for sct in self.active_connections[session_id]['students'] if sct['socket'] != websocket]

        # clean up empty session
        session = self.active_connections[session_id]
        if session["teacher"] is None and len(session["students"]) == 0:
            del self.active_connections[session_id]
    
    def store_peer_connection(self, session_id : str, role : str, websocket : WebSocket, pc):
        if session_id not in self.active_connections:
            return
        
        if role == "teacher":
            if self.active_connections[session_id]['teacher']:
                self.active_connections[session_id]['teacher']['peer_connection'] = pc
        else:
            for student in self.active_connections[session_id]['students']:
                if student["socket"] == websocket:
                    student['peer_connection'] = pc
                    break
    
    def get_students(self, session_id : str) -> list:
        if session_id not in self.active_connections:
            return []
        else:
            return self.active_connections[session_id]['students']
    
    def get_teacher_tracks(self, session_id: str) -> list:
        if session_id not in self.active_connections:
            return []
        teacher = self.active_connections[session_id].get("teacher")
        if teacher is None:
            return []
        return teacher.get("tracks", [])

    def store_teacher_tracks(self, session_id: str, tracks: list):
        if session_id not in self.active_connections:
            return
        teacher = self.active_connections[session_id].get("teacher")
        if teacher:
            teacher["tracks"] = tracks

socket_manager = SessionManager()

@router.get("/join")
async def join_session(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": "sevak stream"
        }
    )

@router.get("/{session_id}/")
async def get_session(session_id: str, role : str, name : str, request : Request):
    return templates.TemplateResponse(
        request=request,
        name="room.html",
        context = {
            "session_id": session_id,
            "role": role,
            "name": name
        }
    )

@router.websocket('/ws/{session_id}/')
async def join_session(
    websocket : WebSocket,
    session_id : str,
    role : str, # this will store the role of the person.
    name : str, # this will store the name of the uesr connecting to the websocket.
    ):
    await socket_manager.connect(websocket, session_id, role, name)
    pc = None
    recorder = None
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get('type')

            if msg_type == "offer":
                pc, recorder = await handle_offer(
                    data=data,
                    websocket=websocket,
                    session_id=session_id,
                    role=role,
                    get_student_callback=lambda: socket_manager.get_students(session_id),
                    store_tracks_callback=lambda tracks: socket_manager.store_teacher_tracks(session_id, tracks),
                    get_teacher_tracks_callback=lambda: socket_manager.get_teacher_tracks(session_id)
                )
                socket_manager.store_peer_connection(
                    session_id=session_id,
                    role=role,
                    websocket=websocket,
                    pc=pc
                )
                
            elif msg_type == "ice-candidate":
                # add client's ICE candidate to server's peer connection
                await handle_ice_candidate(data, pc)

            else:
                print("unknows message type ", msg_type)
            

    except WebSocketDisconnect:
        if recorder:
            await recorder.stop()
        if pc:
            await pc.close()
            print(f"[{session_id}] {role} - {name} disconnected, pc closed")
            
        socket_manager.disconnect(websocket, session_id, role)
