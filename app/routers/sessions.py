from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from app.dependencies import templates

router = APIRouter(
    prefix="/session",
    tags=['Session']
)

class SocketManager:
    def __init__(self):
        self.active_connections : dict[str, dict] = {}
        '''
        {
            "#session-123" : {
                "teacher" : {"socket": <WebSocket>, "name": "guru sevak singh"},
                "students" : [
                    {"socket": <WebSocket, "name": "Student 1"},
                    {"socket": <WebSocket, "name": "Student 1"},
                    {"socket": <WebSocket, "name": "Student 1"}
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
        
        socket_data = {"name": name, 'websocket' : websocket}
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
            self.active_connections[session_id]['students'] = [sct for sct in self.active_connections[session_id]['students'] if sct['websocket'] != websocket]

        # clean up empty session
        session = self.active_connections[session_id]
        if session["teacher"] is None and len(session["students"]) == 0:
            del self.active_connections[session_id]


socket_manager = SocketManager()

@router.get("/join")
async def join_session(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": "sevak stream"
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
    try:
        while True:
            data = await websocket.receive_json()
            print(data)

    except WebSocketDisconnect:
        await socket_manager.disconnect(websocket, session_id, role)