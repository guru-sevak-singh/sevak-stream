from fastapi import WebSocket
from aiortc import RTCPeerConnection, RTCSessionDescription
import json
from aiortc.contrib.media import MediaRecorder


async def handle_offer(
    data: dict,
    websocket: WebSocket,
    session_id: str,
    role: str,
    get_student_callback=None,
    store_tracks_callback=None,    # ← new
    get_teacher_tracks_callback=None  # ← new
):
    pc = RTCPeerConnection()
    recorder = None
    collected_tracks = []   # collect teacher's tracks here

    if role == "teacher":
        import os
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
            recorder.addTrack(track)
            track_received[track.kind] = True
            collected_tracks.append(track)

            # store tracks so late joining students can get them
            if store_tracks_callback:
                store_tracks_callback(collected_tracks)

            if track_received["audio"] and track_received["video"]:
                await recorder.start()
                print("Recording started")

    # if student — add teacher's existing tracks BEFORE answering
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

async def handle_ice_candidate(data : dict, pc : RTCPeerConnection):
    if pc is None:
        print("No Peer Connection Found...")
        return
    
    candidate_data = data.get("candidate")
    # from aiortc.contrib.media import RTCIceCandidate
    # aiortc handles candidates differently
    # for now just print — we'll refine this
    print(f"ICE candidate received: {candidate_data}")
