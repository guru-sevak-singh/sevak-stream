import os
from fastapi import WebSocket
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder


async def handle_offer(
    data: dict,
    websocket: WebSocket,
    session_id: str,
    role: str,
    store_track_callback=None,
    get_teacher_tracks_callback=None,
    notify_students_callback=None
):
    '''
    Creates WebRTC peer connection between client and server.

    Teacher flow:
    - server receives audio/video tracks from teacher
    - stores each track in SessionManager via callback
    - starts recording when both tracks arrive
    - notifies all waiting students that session is live

    Student flow:
    - server checks if teacher tracks exist already
    - adds them to student pc BEFORE answering
    - single clean offer/answer — no renegotiation needed
    '''
    pc = RTCPeerConnection()
    recorder = None

    if role == "teacher":
        os.makedirs("recordings", exist_ok=True)
        recorder = MediaRecorder(f"recordings/{session_id}.mp4")

    track_received = {"audio": False, "video": False}

    @pc.on("icecandidate")
    async def on_ice_candidate(candidate):
        if candidate:
            await websocket.send_json({
                "type": "ice-candidate",
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                }
            })

    @pc.on("track")
    async def on_track(track):
        print(f"Track received — kind: {track.kind}")

        if role == "teacher":
            # add to recorder
            recorder.addTrack(track)
            track_received[track.kind] = True

            # store raw track in SessionManager one at a time
            if store_track_callback:
                store_track_callback(track)

            # start recording only when BOTH tracks have arrived
            if track_received["audio"] and track_received["video"]:
                await recorder.start()
                print("Recording started")

                # notify all waiting students — teacher is live
                if notify_students_callback:
                    await notify_students_callback()

    # student — get teacher's tracks and add BEFORE answering
    # relay gives each student an independent subscription
    # so one student disconnecting never affects others
    if role == "student" and get_teacher_tracks_callback:
        teacher_tracks = get_teacher_tracks_callback()
        for track in teacher_tracks:
            pc.addTrack(track)
        print(f"Added {len(teacher_tracks)} teacher tracks to student pc")

    offer = RTCSessionDescription(
        sdp=data.get("sdp").get("sdp"),
        type=data.get("sdp").get("type")
    )
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    await websocket.send_json({
        "type": "answer",
        "sdp": {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }
    })

    return pc, recorder


async def handle_ice_candidate(data: dict, pc: RTCPeerConnection):
    '''
    Receives ICE candidate from client and adds to peer connection.
    Without this WebRTC connection is unreliable.
    ICE candidates help find best network path between client and server.
    '''
    if pc is None:
        print("No peer connection — ignoring ICE candidate")
        return

    candidate_data = data.get("candidate")
    if not candidate_data:
        return

    try:
        from aiortc.sdp import candidate_from_sdp

        candidate_str = candidate_data.get("candidate", "")

        if candidate_str:
            # remove "candidate:" prefix if present
            if candidate_str.startswith("candidate:"):
                candidate_str = candidate_str[10:]

            sdp_candidate = candidate_from_sdp(candidate_str)
            sdp_candidate.sdpMid = candidate_data.get("sdpMid")
            sdp_candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")

            await pc.addIceCandidate(sdp_candidate)
            print("ICE candidate added successfully")

    except Exception as e:
        print(f"ICE candidate error — {e}")